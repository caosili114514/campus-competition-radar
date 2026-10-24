"""采集编排：逐来源容错、历史合并、链接事实核验与报告输出。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import uuid

from .config import (
    ConfigError,
    SOURCE_STATUS_LABELS,
    default_source_state,
    load_sources,
)
from .dates import TZ, as_iso, normalize_text, parse_datetime
from .dedupe import merge_incoming
from .extractors import extract_items
from .fetcher import DEFAULT_USER_AGENT, FixtureFetcher, HttpFetcher
from .link_checker import check_link
from .parsers import extract_main_content, parse_items, strip_html
from .quality import build_quality_report
from .schema import (
    DATA_NOTICE,
    SCHEMA_VERSION,
    normalize_competition_record,
    now_iso,
)

DEFAULT_OUTPUT_DIR = Path("docs/data")
SUCCESS_SOURCE_STATUSES = {"success", "empty"}
FAILURE_SOURCE_STATUSES = {"fetch_failed", "parse_failed", "config_error"}


@dataclass
class RunOptions:
    sources_path: Path
    output_dir: Path
    max_records: int = 200
    dry_run: bool = False
    fixtures_dir: Path | None = None
    check_links: bool = True
    respect_robots: bool = True
    link_check_limit: int = 50
    timeout: float = 15.0
    retries: int = 2
    request_delay: float = 1.0
    force: bool = False
    user_agent: str = DEFAULT_USER_AGENT


@dataclass
class RunOutcome:
    run_id: str
    started_at: str
    finished_at: str
    status: str
    message: str
    records: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    written_paths: list[str] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    dry_run: bool = False
def make_run_id(now: datetime) -> str:
    return "run_" + now.strftime("%Y%m%dT%H%M%S%z") + "_" + uuid.uuid4().hex[:6]


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取已有数据文件 {path}: {exc}") from exc


def _append_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def _log_entry(run_id: str, level: str, event: str, message: str,
               details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "run_id": run_id,
        "level": level,
        "event": event,
        "message": message,
        "details": details or {},
    }
def read_existing_live_records(path: Path) -> tuple[list[dict[str, Any]], int, str | None]:
    """读取历史；演示记录不会混入 live 数据。返回 (live记录, 忽略演示数, 旧data_mode)。"""
    if not path.exists():
        return [], 0, None
    data = _read_json(path, {})
    if isinstance(data, list):
        raw_records = data
        old_mode = "live"
    elif isinstance(data, dict):
        raw_records = data.get("records") or []
        old_mode = data.get("data_mode")
    else:
        raise ConfigError("已有 competitions.json 顶层必须是对象或数组")
    if not isinstance(raw_records, list):
        raise ConfigError("已有 competitions.json 的 records 必须是数组")
    live: list[dict[str, Any]] = []
    ignored_demo = 0
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        if raw.get("is_demo") is True:
            ignored_demo += 1
            continue
        live.append(normalize_competition_record(raw))
    return live, ignored_demo, old_mode


def read_run_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = _read_json(path, {})
    history = data.get("run_history") if isinstance(data, dict) else None
    return list(history) if isinstance(history, list) else []
def _keyword_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ConfigError("title 关键词过滤配置必须是字符串或字符串数组")


def apply_source_filters(items: list[dict[str, Any]], source: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    """按 URL 正则、标题关键词过滤，再应用单来源本次条数上限。"""
    include_keywords = _keyword_values(source.get("title_include_keywords"))
    exclude_keywords = _keyword_values(source.get("title_exclude_keywords"))
    pattern_text = source.get("url_include_pattern")
    pattern = re.compile(pattern_text, re.I) if pattern_text else None
    matched: list[dict[str, Any]] = []
    filtered_count = 0
    for item in items:
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        if pattern and not pattern.search(url):
            filtered_count += 1
            continue
        if include_keywords and not any(keyword.casefold() in title.casefold() for keyword in include_keywords):
            filtered_count += 1
            continue
        if exclude_keywords and any(keyword.casefold() in title.casefold() for keyword in exclude_keywords):
            filtered_count += 1
            continue
        matched.append(item)
    limit = source.get("max_items_per_run")
    if limit is None:
        limit = source.get("max_records")
    if limit is not None:
        limit = max(0, int(limit))
        matched = matched[:limit]
    return matched, filtered_count, len(matched)
def check_robots_permission(url: str, fetcher: Any, user_agent: str, *,
                            checked_at: str | None = None) -> dict[str, Any]:
    """获取并检查 robots.txt；Disallow、401/403 或不可确认时跳过来源。"""
    parts = urlsplit(url)
    if parts.scheme == "fixture":
        return {"allowed": True, "robots_url": None, "http_status": None,
                "reason": "fixture 本地来源不访问网络，跳过 robots.txt 检查",
                "checked_at": checked_at or now_iso()}
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return {"allowed": False, "robots_url": None, "http_status": None,
                "reason": "来源地址无效，无法检查 robots.txt",
                "checked_at": checked_at or now_iso()}
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        result = fetcher.fetch(robots_url, headers={"User-Agent": user_agent})
    except Exception as exc:
        return {"allowed": False, "robots_url": robots_url, "http_status": None,
                "reason": f"robots.txt 抓取异常，谨慎跳过来源: {type(exc).__name__}: {exc}",
                "checked_at": checked_at or now_iso()}
    status = result.status_code
    if result.timed_out:
        reason = "robots.txt 请求超时，谨慎跳过来源"
        allowed = False
    elif status in (401, 403):
        reason = f"robots.txt 返回 HTTP {status}，视为禁止抓取"
        allowed = False
    elif status is not None and 200 <= status < 300:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse((result.text or "").splitlines())
        allowed = parser.can_fetch(user_agent, url)
        reason = "robots.txt 允许抓取" if allowed else "robots.txt 明确 Disallow 此路径"
    elif status == 404:
        allowed = True
        reason = "robots.txt 返回 404，按不存在处理"
    elif status is not None and 300 <= status < 400:
        allowed = False
        reason = f"robots.txt 返回 HTTP {status} 重定向，未确认最终规则，谨慎跳过"
    else:
        allowed = False
        reason = f"robots.txt 不可确认（HTTP {status}），谨慎跳过来源"
    return {"allowed": allowed, "robots_url": robots_url, "http_status": status,
            "reason": reason, "checked_at": checked_at or now_iso()}
def _failure_reason(result: Any) -> str:
    if getattr(result, "error", None):
        return str(result.error)
    status = getattr(result, "status_code", None)
    if status is not None:
        return f"HTTP {status}"
    if getattr(result, "timed_out", False):
        return "请求超时"
    return "未知抓取错误"


def _mark_source_failure(state: dict[str, Any], status: str, reason: str,
                         *, checked_at: str, http_status: int | None = None) -> None:
    state["status"] = status
    state["last_checked_at"] = checked_at
    state["failure_reason"] = reason
    state["result"] = f"失败：{reason}"
    state["http_status"] = http_status
    state["needs_manual_verification"] = True


def _local_link_error(url: str, error: str) -> dict[str, Any]:
    return {
        "url": url,
        "checked_at": now_iso(),
        "status": "connection_error",
        "status_label": "连接错误",
        "http_status": None,
        "final_url": url,
        "redirected": False,
        "js_page_detected": False,
        "error": error,
        "content_type": None,
        "registration_open_claim": False,
        "note": "仅记录 HTTP 事实，不代表报名开放、资格有效或主办方确认。",
    }
def run_collection(options: RunOptions, *, fetcher: Any | None = None,
                   link_check_func: Callable[[str], dict[str, Any]] | None = None,
                   clock: Callable[[], datetime] | None = None) -> RunOutcome:
    """执行一次采集。单来源失败被隔离，已有 live 历史不会被删除。"""
    if options.max_records < 0:
        raise ConfigError("max_records 必须是非负整数")
    clock_fn = clock or (lambda: datetime.now(TZ))
    started_dt = clock_fn()
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=TZ)
    started_at = as_iso(started_dt) or now_iso()
    run_id = make_run_id(started_dt)
    logs: list[dict[str, Any]] = []

    def log(level: str, event: str, message: str, details: dict[str, Any] | None = None) -> None:
        logs.append(_log_entry(run_id, level, event, message, details))

    sources = load_sources(options.sources_path)
    states = [default_source_state(source) for source in sources]
    for source, state in zip(sources, states):
        state["records_filtered"] = int(state.get("records_filtered") or 0)
        state["records_matched"] = int(state.get("records_matched") or 0)
        state["detail_fetch_attempted"] = 0
        state["detail_fetch_failed"] = 0
        state["robots"] = None
        configured_delay = float(source.get("request_delay_seconds") or 0.0)
        state["effective_request_delay_seconds"] = max(float(options.request_delay), configured_delay)
    enabled_count = sum(1 for source in sources if source.get("enabled") is True)
    log("info", "run_started", "采集任务开始。", {
        "sources": len(sources), "enabled_sources": enabled_count,
        "max_records": options.max_records, "dry_run": options.dry_run,
    })

    if options.dry_run:
        for source, state in zip(sources, states):
            if source.get("enabled"):
                state["status"] = "dry_run"
                state["result"] = "试运行：未发起抓取，未写入任何文件"
                state["failure_reason"] = None
        finished_at = as_iso(clock_fn()) or now_iso()
        message = f"试运行完成：配置 {len(sources)} 个来源，启用 {enabled_count} 个；未抓取、未写文件。"
        log("info", "dry_run_finished", message)
        return RunOutcome(
            run_id=run_id, started_at=started_at, finished_at=finished_at,
            status="dry_run", message=message, sources=states,
            logs=logs, dry_run=True,
        )
    output_dir = Path(options.output_dir)
    competitions_path = output_dir / "competitions.json"
    sources_path = output_dir / "sources.json"
    meta_path = output_dir / "meta.json"
    quality_path = output_dir / "quality-report.json"
    run_log_path = output_dir / "run-log.jsonl"
    existing_records, ignored_demo_count, old_data_mode = read_existing_live_records(competitions_path)
    if ignored_demo_count:
        log("warning", "demo_records_ignored",
            f"已忽略 {ignored_demo_count} 条演示记录，防止演示数据混入 live 输出。",
            {"ignored_demo_count": ignored_demo_count, "old_data_mode": old_data_mode})
    run_history = read_run_history(meta_path)
    previous_sources = read_previous_source_states(sources_path)
    meta_schedule = read_previous_schedule_from_meta(meta_path)
    for source_id, previous in meta_schedule.items():
        previous_sources.setdefault(source_id, previous)
    for source, state in zip(sources, states):
        previous = previous_sources.get(source["id"]) or {}
        if previous.get("last_checked_at"):
            state["last_checked_at"] = previous.get("last_checked_at")
        if previous.get("last_success_at"):
            state["last_success_at"] = previous.get("last_success_at")
    incoming: list[dict[str, Any]] = []
    links_checked = 0

    if fetcher is None:
        if options.fixtures_dir is not None:
            client: Any = FixtureFetcher(options.fixtures_dir, user_agent=options.user_agent)
        else:
            client = HttpFetcher(
                timeout=options.timeout, retries=options.retries,
                request_delay=options.request_delay, user_agent=options.user_agent,
            )
    else:
        client = fetcher
    offline_fixture_mode = options.fixtures_dir is not None
    for index, (source, state) in enumerate(zip(sources, states)):
        if not source.get("enabled"):
            state["status"] = "disabled"
            state["result"] = "未启用，本次未发起抓取，也未做任何验证"
            log("info", "source_disabled", f"来源 {source['name']} 未启用，跳过。",
                {"source_id": source["id"]})
            continue
        previous_state = previous_sources.get(source["id"])
        due, schedule_reason = source_schedule_decision(
            source, previous_state, started_dt, force=options.force
        )
        state["schedule_decision"] = schedule_reason
        if not due:
            frequency = str(source.get("update_frequency") or "daily").lower()
            state["status"] = "manual_skipped" if frequency == "manual" else "not_due"
            state["result"] = schedule_reason
            state["failure_reason"] = None
            log("info", "source_schedule_skipped",
                f"来源 {source['name']} 因调度规则跳过：{schedule_reason}",
                {"source_id": source["id"], "update_frequency": frequency,
                 "schedule_decision": schedule_reason})
            continue
        checked_at = started_at
        state["last_checked_at"] = checked_at
        effective_delay = float(state.get("effective_request_delay_seconds") or 0.0)
        if hasattr(client, "set_request_delay"):
            client.set_request_delay(effective_delay)
        elif hasattr(client, "request_delay"):
            client.request_delay = effective_delay
        log("info", "source_request_delay",
            f"来源 {source['name']} 生效请求间隔 {effective_delay:g} 秒。",
            {"source_id": source["id"], "effective_request_delay_seconds": effective_delay,
             "global_request_delay": options.request_delay,
             "source_request_delay": source.get("request_delay_seconds")})
        if options.respect_robots:
            robots = check_robots_permission(source["list_url"], client, options.user_agent,
                                              checked_at=checked_at)
            state["robots"] = robots
            log("info" if robots["allowed"] else "warning", "robots_checked",
                f"来源 {source['name']} robots.txt 检查：{robots['reason']}",
                {"source_id": source["id"], "robots": robots})
            if not robots["allowed"]:
                state["status"] = "robots_blocked"
                state["result"] = f"遵守 robots.txt，未抓取：{robots['reason']}"
                state["failure_reason"] = robots["reason"]
                state["needs_manual_verification"] = True
                continue
        try:
            result = client.fetch(source["list_url"])
        except Exception as exc:
            _mark_source_failure(state, "fetch_failed", f"{type(exc).__name__}: {exc}", checked_at=checked_at)
            log("error", "source_fetch_failed", f"来源 {source['name']} 抓取失败：{exc}",
                {"source_id": source["id"]})
            continue
        state["http_status"] = result.status_code
        if not result.ok:
            reason = _failure_reason(result)
            _mark_source_failure(state, "fetch_failed", reason, checked_at=checked_at,
                                 http_status=result.status_code)
            log("error", "source_fetch_failed", f"来源 {source['name']} 抓取失败：{reason}",
                {"source_id": source["id"], "http_status": result.status_code})
            continue
        try:
            raw_items = parse_items(result.text, source, base_url=result.final_url or source["list_url"])
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            _mark_source_failure(state, "parse_failed", reason, checked_at=checked_at,
                                 http_status=result.status_code)
            log("error", "source_parse_failed", f"来源 {source['name']} 解析失败：{reason}",
                {"source_id": source["id"]})
            continue
        state["records_found"] = len(raw_items)
        try:
            filtered_items, filtered_count, matched_count = apply_source_filters(raw_items, source)
        except Exception as exc:
            reason = f"过滤配置错误: {type(exc).__name__}: {exc}"
            _mark_source_failure(state, "config_error", reason, checked_at=checked_at,
                                 http_status=result.status_code)
            log("error", "source_filter_failed", f"来源 {source['name']} 过滤失败：{reason}",
                {"source_id": source["id"]})
            continue
        state["records_filtered"] = filtered_count
        state["records_matched"] = matched_count
        enriched_items: list[dict[str, Any]] = []
        detail_errors: list[str] = []
        detail_max = source.get("max_items_per_run")
        if detail_max is None:
            detail_max = options.max_records
        detail_limit = min(len(filtered_items), max(0, int(detail_max)))
        for item in filtered_items[:detail_limit]:
            enriched = enrich_item_from_detail(item, source, client, fetched_at=started_at)
            detail_info = enriched.get("detail_fetch") or {}
            if detail_info.get("error"):
                detail_errors.append(f"{enriched.get('url') or '(无链接)'}: {detail_info.get('error')}")
            enriched_items.append(enriched)
        enriched_items.extend(filtered_items[detail_limit:])
        state["detail_fetch_attempted"] = detail_limit
        state["detail_fetch_failed"] = len(detail_errors)
        if detail_errors:
            log("warning", "detail_fetch_partial",
                f"来源 {source['name']} 有 {len(detail_errors)} 条详情页抓取失败，已保留列表摘要。",
                {"source_id": source["id"], "errors": detail_errors[:5]})
        extract_errors: list[str] = []
        records, extract_errors = extract_items(enriched_items, source, now=started_at)
        state["records_matched"] = len(records)
        if not records:
            state["status"] = "empty"
            state["last_success_at"] = started_at
            state["result"] = "抓取成功，但过滤和抽取后没有可输出记录"
            if detail_errors:
                state["result"] += f"；详情页失败 {len(detail_errors)} 条"
            if extract_errors:
                state["result"] += f"；{len(extract_errors)} 条抽取失败"
            log("warning", "source_empty", f"来源 {source['name']} 没有可输出记录。",
                {"source_id": source["id"], "extracted_errors": extract_errors[:3]})
            continue
        can_link_check = (options.check_links and not offline_fixture_mode) or link_check_func is not None
        if can_link_check:
            for record in records:
                checked_facts: list[tuple[str, dict[str, Any]]] = []
                for fact_field, url_field in (
                    ("link_check", "official_notice_url"),
                    ("registration_link_check", "registration_url"),
                ):
                    if links_checked >= options.link_check_limit:
                        break
                    url = record.get(url_field)
                    if not url:
                        continue
                    try:
                        fact = link_check_func(url) if link_check_func else check_link(url, client)
                    except Exception as exc:
                        fact = _local_link_error(url, f"{type(exc).__name__}: {exc}")
                    record[fact_field] = fact
                    links_checked += 1
                    checked_facts.append((fact_field, fact))
                if not checked_facts:
                    continue
                bad_facts = [
                    (field, fact) for field, fact in checked_facts
                    if fact.get("status") != "ok"
                ]
                labels = {
                    "link_check": "通知链接",
                    "registration_link_check": "报名链接",
                }
                summary_parts = [
                    f"{labels.get(field, field)}={fact.get('status_label')}"
                    for field, fact in checked_facts
                ]
                summary_text = "；".join(summary_parts)
                if any(fact.get("status") == "not_found" for _, fact in checked_facts):
                    record["verification_status"] = "broken"
                    record["verification_notes"] = (
                        f"链接核验事实：{summary_text}。存在 404，需人工核验；"
                        "不代表赛事本身不存在。"
                    )
                elif bad_facts:
                    record["verification_status"] = "pending"
                    record["verification_notes"] = (
                        f"链接核验事实：{summary_text}。仅记录 HTTP 事实，需人工核验；"
                        "不代表报名开放或报名有效。"
                    )
                else:
                    record["verification_notes"] = (
                        f"链接核验事实：{summary_text}。HTTP 可达不代表报名开放或报名有效，"
                        "赛事与报名资格仍需人工核验。"
                    )
        state["status"] = "success"
        state["last_success_at"] = started_at
        state["result"] = f"抓取成功，解析 {len(raw_items)} 条候选，过滤后 {len(records)} 条"
        if detail_errors:
            state["result"] += f"；详情页失败 {len(detail_errors)} 条，已保留列表摘要"
        if extract_errors:
            state["result"] += f"；{len(extract_errors)} 条抽取失败"
        state["needs_manual_verification"] = not bool(source.get("verified"))
        incoming.extend(records)
        log("info", "source_success",
            f"来源 {source['name']} 完成：候选 {len(raw_items)}，过滤后 {len(records)}，抽取 {len(records)}。",
            {"source_id": source["id"], "filtered": filtered_count})
    merged = merge_incoming(existing_records, incoming, now=started_at,
                            max_new=max(0, int(options.max_records)))
    final_records = merged.records
    for source, state in zip(sources, states):
        stats = merged.stats_by_source.get(source["id"])
        if stats:
            state["records_added"] = stats.get("added", 0)
            state["records_updated"] = stats.get("updated", 0)
            state["records_duplicates"] = stats.get("unchanged", 0)
            if stats.get("skipped"):
                state["result"] += f"；本次新增上限已跳过 {stats['skipped']} 条新记录"
    success_count = sum(1 for state in states if state.get("status") in SUCCESS_SOURCE_STATUSES)
    failure_count = sum(1 for state in states if state.get("status") in FAILURE_SOURCE_STATUSES)
    robots_blocked_count = sum(1 for state in states if state.get("status") == "robots_blocked")
    not_due_count = sum(1 for state in states if state.get("status") == "not_due")
    manual_skipped_count = sum(1 for state in states if state.get("status") == "manual_skipped")
    skipped_count = not_due_count + manual_skipped_count + robots_blocked_count
    if enabled_count == 0:
        collection_status = "no_enabled_sources"
    elif success_count == 0 and failure_count == 0 and skipped_count > 0:
        collection_status = "skipped"
    elif success_count == 0:
        collection_status = "failed"
    elif failure_count:
        collection_status = "partial_failure"
    else:
        collection_status = "success"
    pending_verification_count = sum(
        1 for record in final_records
        if record.get("verification_status") in ("pending", "incomplete")
    )
    finished_at = as_iso(clock_fn()) or now_iso()
    record_count = len(final_records)
    if collection_status == "no_enabled_sources":
        message = "本次没有启用信息源；已生成空 live 数据，未抓取、未核验，空数据不代表没有赛事。"
    elif collection_status == "skipped":
        message = (
            f"按 update_frequency/robots.txt 规则跳过 {skipped_count} 个启用来源"
            f"（未到周期 {not_due_count}，manual {manual_skipped_count}，robots {robots_blocked_count}）；"
            f"保留历史 {record_count} 条记录，本次未新增。"
        )
    elif collection_status == "failed":
        message = f"启用来源均未成功；保留历史 {record_count} 条记录。"
    elif collection_status == "partial_failure":
        message = f"部分来源成功，部分失败；共输出 {record_count} 条 live 记录，全部仍需人工核验。"
    else:
        message = f"采集完成；共输出 {record_count} 条 live 记录，全部仍需人工核验。"
    competitions_doc = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": "live",
        "generated_at": finished_at,
        "notice": DATA_NOTICE,
        "record_count": record_count,
        "records": final_records,
    }
    sources_notice = (
        "来源 verified=false 表示尚未人工确认抓取许可、页面结构、正文真实性与主办方授权；"
        "列表页 HTTP 200 只是当时的可访问事实，不构成验证。"
    )
    sources_doc = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": "live",
        "generated_at": finished_at,
        "notice": sources_notice,
        "source_count": len(states),
        "enabled_count": enabled_count,
        "sources": states,
    }
    run_entry = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": collection_status,
        "message": message,
        "source_count": len(states),
        "success_count": success_count,
        "failure_count": failure_count,
        "robots_blocked_count": robots_blocked_count,
        "not_due_count": not_due_count,
        "manual_skipped_count": manual_skipped_count,
        "skipped_count": skipped_count,
        "records_added": merged.added,
        "records_updated": merged.updated,
        "content_changed": merged.content_changed,
        "record_count": record_count,
        "pending_verification_count": pending_verification_count,
    }
    history = run_history[-49:] + [run_entry]
    meta_doc = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": "live",
        "generated_at": finished_at,
        "last_run": {
            "started_at": started_at,
            "finished_at": finished_at,
            "status": collection_status,
            "message": message,
        },
        "summary": {
            "source_count": len(states),
            "success_count": success_count,
            "failure_count": failure_count,
            "skipped_count": skipped_count,
            "record_count": record_count,
            "pending_verification_count": pending_verification_count,
            "enabled_source_count": enabled_count,
            "robots_blocked_count": robots_blocked_count,
            "not_due_count": not_due_count,
            "manual_skipped_count": manual_skipped_count,
            "skipped_count": skipped_count,
        },
        "run_history": history,
        "source_schedule": [
            {
                "id": state.get("id"),
                "update_frequency": state.get("update_frequency"),
                "last_checked_at": state.get("last_checked_at"),
                "last_success_at": state.get("last_success_at"),
                "status": state.get("status"),
            }
            for state in states
        ],
        "notice": DATA_NOTICE,
    }
    quality_doc = build_quality_report(final_records, states, generated_at=finished_at, data_mode="live")
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(competitions_path, competitions_doc)
    _write_json_atomic(sources_path, sources_doc)
    _write_json_atomic(meta_path, meta_doc)
    _write_json_atomic(quality_path, quality_doc)
    written_paths = [str(competitions_path), str(sources_path), str(meta_path), str(quality_path)]
    log("info", "run_finished", message, {
        "status": collection_status,
        "record_count": record_count,
        "records_added": merged.added,
        "records_updated": merged.updated,
        "content_changed": merged.content_changed,
        "links_checked": links_checked,
        "written_paths": written_paths,
    })
    _append_jsonl(run_log_path, logs)
    written_paths.append(str(run_log_path))
    return RunOutcome(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        status=collection_status,
        message=message,
        records=final_records,
        sources=states,
        meta=meta_doc,
        quality=quality_doc,
        written_paths=written_paths,
        logs=logs,
    )
def _detail_error_status(result: Any) -> str:
    if getattr(result, "timed_out", False):
        return "timeout"
    status = getattr(result, "status_code", None)
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status is not None and status >= 500:
        return "server_error"
    if status is not None:
        return "http_error"
    return "connection_error"
def enrich_item_from_detail(item: dict[str, Any], source: dict[str, Any], fetcher: Any, *,
                            fetched_at: str) -> dict[str, Any]:
    """顺序抓取单个公开详情页并抽取正文；失败只影响该条记录。"""
    enriched = deepcopy(item)
    url = enriched.get("url")
    if not url:
        enriched["detail_fetch"] = {
            "attempted": False, "status": "skipped", "http_status": None,
            "final_url": None, "same_domain": None, "content_source": None,
            "error": "列表候选缺少详情链接", "fetched_at": fetched_at,
        }
        return enriched
    try:
        result = fetcher.fetch(url)
    except Exception as exc:
        enriched["detail_fetch"] = {
            "attempted": True, "status": "connection_error", "http_status": None,
            "final_url": url, "same_domain": None, "content_source": None,
            "error": f"{type(exc).__name__}: {exc}", "fetched_at": fetched_at,
        }
        return enriched
    if not result.ok:
        enriched["detail_fetch"] = {
            "attempted": True, "status": _detail_error_status(result),
            "http_status": result.status_code, "final_url": result.final_url,
            "same_domain": None, "content_source": None,
            "error": _failure_reason(result), "fetched_at": fetched_at,
        }
        return enriched
    if not result.text or not result.text.strip():
        enriched["detail_fetch"] = {
            "attempted": True, "status": "empty_body", "http_status": result.status_code,
            "final_url": result.final_url, "same_domain": None, "content_source": None,
            "error": "详情页响应正文为空", "fetched_at": fetched_at,
        }
        return enriched
    content_type = (result.content_type or "").lower()
    if "html" in content_type or result.text.lstrip().startswith("<"):
        main = extract_main_content(result.text)
    else:
        raw_text = normalize_text(strip_html(result.text))
        main = {"title": None, "content": raw_text[:12000] or None,
                "summary": raw_text[:500] or None, "published_at": None,
                "content_source": "plain_text"}
    source_host = (urlsplit(source.get("list_url") or "").hostname or "").lower()
    final_host = (urlsplit(result.final_url or url).hostname or "").lower()
    fixture_link = urlsplit(source.get("list_url") or "").scheme == "fixture"
    same_domain = fixture_link or bool(source_host and source_host == final_host)
    existing_content = normalize_text(enriched.get("content") or enriched.get("summary"))
    detail_content = normalize_text(main.get("content"))
    if detail_content and (len(detail_content) >= 30 or len(detail_content) > len(existing_content)):
        enriched["content"] = detail_content[:12000]
        enriched["summary"] = normalize_text(main.get("summary") or detail_content[:500]) or None
    if not enriched.get("title") and main.get("title"):
        enriched["title"] = main["title"]
    if main.get("published_at"):
        enriched["published_at"] = main["published_at"]
    if same_domain and result.final_url:
        enriched["url"] = result.final_url
    enriched["detail_fetch"] = {
        "attempted": True, "status": "ok", "http_status": result.status_code,
        "final_url": result.final_url, "same_domain": same_domain,
        "content_source": main.get("content_source"), "error": None,
        "fetched_at": fetched_at,
    }
    return enriched
def read_previous_source_states(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    raw_sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(raw_sources, list):
        return {}
    return {
        str(item.get("id")): item for item in raw_sources
        if isinstance(item, dict) and item.get("id")
    }


def source_schedule_decision(source: dict[str, Any], previous: dict[str, Any] | None,
                             now: datetime, *, force: bool = False) -> tuple[bool, str]:
    """按 update_frequency 做保守调度；manual 不参与自动运行。"""
    frequency = str(source.get("update_frequency") or "daily").strip().lower()
    if force:
        return True, "force=true，忽略 update_frequency 调度"
    if frequency == "manual":
        return False, "manual 来源不参与自动定时抓取；仅允许手动或 --force"
    last_raw = (previous or {}).get("last_success_at")
    last_iso = parse_datetime(last_raw)
    if not last_iso:
        return True, f"无历史成功时间，按 {frequency} 频率执行"
    last_dt = datetime.fromisoformat(last_iso)
    tolerate_hours = {
        "hourly": 0.75,
        "daily": 20.0,
        "weekly": 144.0,
        "monthly": 600.0,
    }.get(frequency)
    if tolerate_hours is None:
        return True, f"未知频率 {frequency}，按每次运行检查处理"
    if now - last_dt < timedelta(hours=tolerate_hours):
        return False, (
            f"未到 {frequency} 调度周期（上次成功 {last_iso}，"
            f"当前 {as_iso(now)}）"
        )
    return True, f"已到 {frequency} 调度周期"
def read_previous_schedule_from_meta(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    schedule = payload.get("source_schedule") if isinstance(payload, dict) else None
    if not isinstance(schedule, list):
        return {}
    return {
        str(item.get("id")): item for item in schedule
        if isinstance(item, dict) and item.get("id")
    }