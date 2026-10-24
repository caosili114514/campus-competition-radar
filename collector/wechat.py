"""手动提交微信公众号公开链接的合规入口。

仅 GET 公开页面；不登录、不提交验证码、不伪造 Cookie、不绕过访问控制。
解析失败时生成 manual-pending.json 待核验任务；成功也只标记 pending，不等于已核实。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import uuid
from urllib.parse import urlsplit

from .dates import TZ, as_iso
from .dedupe import canonicalize_url, merge_incoming
from .extractors import extract_item
from .fetcher import DEFAULT_USER_AGENT, HttpFetcher
from .link_checker import classify_fetch_result
from .manual import (
    MANUAL_NOTICE,
    build_pending_document,
    create_pending_task,
    load_pending_tasks,
    upsert_pending_task,
    write_json_atomic,
)
from .parsers import extract_main_content
from .run import (
    _append_jsonl,
    _failure_reason,
    _log_entry,
    check_robots_permission,
    read_existing_live_records,
)
from .schema import DATA_NOTICE, SCHEMA_VERSION, normalize_competition_record, now_iso

MANUAL_SOURCE = {
    "id": "manual_wechat",
    "name": "微信公众号（手动公开链接）",
    "domain": "mp.weixin.qq.com",
    "list_url": None,
    "source_type": "manual",
    "enabled": False,
    "verified": False,
    "is_demo": False,
}

BLOCK_MARKERS = (
    "环境异常", "完成验证", "请输入验证码", "请先登录", "登录后继续",
    "访问过于频繁", "captcha", "security check", "verify you are human",
)


@dataclass
class ManualResult:
    status: str
    message: str
    url: str
    output_dir: str
    pending_path: str | None = None
    competitions_path: str | None = None
    task: dict | None = None
    record_id: str | None = None
    dry_run: bool = False
def _valid_public_url(url: str) -> tuple[bool, str]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False, "URL 无法解析"
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False, "只接受 http/https 公开页面链接"
    if parts.hostname and parts.hostname.lower() not in ("mp.weixin.qq.com", "weixin.qq.com"):
        return False, "本入口只处理微信公众号公开链接（mp.weixin.qq.com / weixin.qq.com）"
    return True, ""


def _blocked_reason(text: str, title: str, content: str) -> str | None:
    lower = f"{title} {text}".lower()
    if any(marker.lower() in lower for marker in BLOCK_MARKERS):
        if len(content) < 200:
            return "页面出现登录/验证码/访问受限提示，未绕过，转人工核验"
    if len(content) < 40:
        return "公开页未解析出可读正文，可能为 JavaScript 渲染或需要人工打开"
    return None
def _write_manual_log(output_dir: Path, run_id: str, level: str, event: str,
                      message: str, details: dict) -> None:
    entry = _log_entry(run_id, level, event, message, details)
    _append_jsonl(output_dir / "run-log.jsonl", [entry])


def _pending_result(output_dir: Path, url: str, reason: str, *, run_id: str,
                    http_status: int | None = None, error: str | None = None,
                    robots: dict | None = None, requested_at: str) -> ManualResult:
    pending_path = output_dir / "manual-pending.json"
    tasks = load_pending_tasks(pending_path)
    task = create_pending_task(
        url, reason, http_status=http_status, error=error,
        robots=robots, requested_at=requested_at,
    )
    tasks = upsert_pending_task(tasks, task)
    write_json_atomic(pending_path, build_pending_document(tasks, generated_at=requested_at))
    _write_manual_log(output_dir, run_id, "warning", "manual_wechat_pending",
                      f"公众号公开链接未自动解析，已写入待核验任务：{reason}",
                      {"url": url, "reason": reason, "http_status": http_status})
    return ManualResult(
        status="pending_manual_review", message=reason, url=url,
        output_dir=str(output_dir), pending_path=str(pending_path), task=task,
    )
def process_wechat_url(url: str, output_dir: str | Path, *, fetcher=None,
                       respect_robots: bool = True, timeout: float = 15.0,
                       retries: int = 1, request_delay: float = 2.0,
                       now: datetime | None = None, dry_run: bool = False) -> ManualResult:
    output = Path(output_dir)
    stamp_dt = now or datetime.now(TZ)
    if stamp_dt.tzinfo is None:
        stamp_dt = stamp_dt.replace(tzinfo=TZ)
    requested_at = as_iso(stamp_dt) or now_iso()
    run_id = "manual_wechat_" + stamp_dt.strftime("%Y%m%dT%H%M%S%z") + "_" + uuid.uuid4().hex[:6]
    valid, reason = _valid_public_url(url)
    if not valid:
        if dry_run:
            return ManualResult("dry_run", reason, url, str(output), dry_run=True)
        return _pending_result(output, url, reason, run_id=run_id, requested_at=requested_at)
    if dry_run:
        return ManualResult(
            "dry_run", "试运行：未抓取公开页，未写入任何文件。", url, str(output), dry_run=True,
        )

    client = fetcher or HttpFetcher(
        timeout=timeout, retries=retries, request_delay=request_delay,
        user_agent=DEFAULT_USER_AGENT,
    )
    robots = None
    if respect_robots:
        robots = check_robots_permission(url, client, DEFAULT_USER_AGENT, checked_at=requested_at)
        if not robots["allowed"]:
            return _pending_result(output, url, robots["reason"], run_id=run_id,
                                   robots=robots, requested_at=requested_at)
    try:
        result = client.fetch(url)
    except Exception as exc:
        return _pending_result(output, url, "公开页抓取异常，未绕过访问限制",
                               run_id=run_id, error=f"{type(exc).__name__}: {exc}",
                               robots=robots, requested_at=requested_at)
    if not result.ok:
        reason = _failure_reason(result)
        if result.status_code in (401, 403):
            reason += "；页面需要登录或拒绝访问，程序未尝试绕过"
        return _pending_result(output, url, reason, run_id=run_id,
                               http_status=result.status_code, error=result.error,
                               robots=robots, requested_at=requested_at)
    page = extract_main_content(result.text)
    page_title = page.get("title") or ""
    page_content = page.get("content") or ""
    blocked = _blocked_reason(result.text, page_title, page_content)
    if blocked:
        return _pending_result(output, url, blocked, run_id=run_id,
                               http_status=result.status_code, robots=robots,
                               requested_at=requested_at)
    final_url = result.final_url or url
    try:
        source_host = (urlsplit(url).hostname or "").lower()
        final_host = (urlsplit(final_url).hostname or "").lower()
    except ValueError:
        source_host = final_host = ""
    official_url = final_url if source_host and source_host == final_host else url
    item = {
        "title": page_title,
        "url": official_url,
        "content": page_content,
        "summary": page.get("summary"),
        "published_at": page.get("published_at"),
    }
    record = extract_item(item, MANUAL_SOURCE, now=requested_at)
    if record is None:
        return _pending_result(output, url, "未能从公开页提取有效标题，转人工核验",
                               run_id=run_id, http_status=result.status_code,
                               robots=robots, requested_at=requested_at)
    record["link_check"] = classify_fetch_result(result, now=requested_at)
    record["verification_status"] = "pending"
    record["last_verified_at"] = None
    record["verification_notes"] = (
        "手动提交的微信公众号公开链接，已用普通 GET 读取；未登录、未提交验证码、未绕过访问控制。"
        "内容仍待人工核验，链接可访问不代表报名开放。"
    )
    record["is_demo"] = False
    record = normalize_competition_record(record, now=requested_at, source=MANUAL_SOURCE)
    output.mkdir(parents=True, exist_ok=True)
    competitions_path = output / "competitions.json"
    existing, _, _ = read_existing_live_records(competitions_path)
    merged = merge_incoming(existing, [record], now=requested_at, max_new=1)
    competitions_doc = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": "live",
        "generated_at": requested_at,
        "notice": DATA_NOTICE,
        "record_count": len(merged.records),
        "records": merged.records,
    }
    write_json_atomic(competitions_path, competitions_doc)
    pending_path = output / "manual-pending.json"
    tasks = load_pending_tasks(pending_path)
    write_json_atomic(pending_path, build_pending_document(tasks, generated_at=requested_at))
    _write_manual_log(output, run_id, "info", "manual_wechat_pending_verification",
                      "微信公众号公开链接已解析并写入 live 记录，仍待人工核验。",
                      {"url": url, "official_notice_url": record.get("official_notice_url"),
                       "record_id": record.get("id"), "http_status": result.status_code})
    return ManualResult(
        status="success_pending_verification",
        message="公开页已解析写入，记录状态为 pending，必须人工核验后才可视为已验证。",
        url=url,
        output_dir=str(output),
        pending_path=str(pending_path),
        competitions_path=str(competitions_path),
        record_id=record.get("id"),
    )
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m collector.wechat",
        description="手动提交微信公众号公开链接（不登录、不绕过验证码）。",
    )
    parser.add_argument("--url", required=True, help="微信公众号公开文章 URL")
    parser.add_argument("--output", required=True, help="输出目录（测试请用临时目录）")
    parser.add_argument("--timeout", type=float, default=15.0, help="请求超时秒数")
    parser.add_argument("--retries", type=int, default=1, help="失败重试次数")
    parser.add_argument("--request-delay", type=float, default=2.0, help="请求间隔秒数")
    parser.add_argument("--dry-run", action="store_true", help="只校验参数，不抓取、不写文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outcome = process_wechat_url(
            args.url, args.output, timeout=args.timeout,
            retries=args.retries, request_delay=args.request_delay,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"处理失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"状态: {outcome.status}")
    print(outcome.message)
    if outcome.pending_path:
        print(f"待核验任务: {outcome.pending_path}")
    if outcome.competitions_path:
        print(f"赛事数据: {outcome.competitions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())