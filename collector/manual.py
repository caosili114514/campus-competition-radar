"""手动提交公开链接的待核验任务辅助函数。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .dates import normalize_text
from .dedupe import canonicalize_url
from .schema import SCHEMA_VERSION, now_iso

MANUAL_NOTICE = (
    "仅登记用户手动提交的公开链接；不登录、不提交验证码、不绕过访问控制、不伪造微信身份。"
    "失败只生成待核验任务，不代表链接无效或赛事不存在。"
)


def pending_task_id(url: str) -> str:
    canonical = canonicalize_url(url) or url
    return "pending_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def create_pending_task(url: str, reason: str, *, http_status: int | None = None,
                        error: str | None = None, robots: dict[str, Any] | None = None,
                        requested_at: str | None = None) -> dict[str, Any]:
    canonical = canonicalize_url(url)
    return {
        "id": pending_task_id(url),
        "url": url,
        "canonical_url": canonical,
        "status": "pending_manual_review",
        "reason": normalize_text(reason) or "公开页无法自动解析",
        "requested_at": requested_at or now_iso(),
        "http_status": http_status,
        "error": normalize_text(error) or None,
        "robots": robots,
        "no_login_bypass": True,
        "compliance_note": "未尝试登录、验证码、Cookie 注入或任何反爬绕过；需人工在浏览器中合法核验。",
    }
def load_pending_tasks(path: str | Path) -> list[dict[str, Any]]:
    task_path = Path(path)
    if not task_path.exists():
        return []
    try:
        with task_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取待核验任务文件: {exc}") from exc
    tasks = data.get("tasks") if isinstance(data, dict) else data
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def build_pending_document(tasks: list[dict[str, Any]], *, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or now_iso(),
        "notice": MANUAL_NOTICE,
        "task_count": len(tasks),
        "tasks": tasks,
    }


def write_json_atomic(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def upsert_pending_task(tasks: list[dict[str, Any]], task: dict[str, Any]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    replaced = False
    for existing in tasks:
        if existing.get("id") == task.get("id"):
            previous_requested = existing.get("requested_at")
            merged = dict(existing)
            merged.update(task)
            if previous_requested:
                merged["first_requested_at"] = existing.get("first_requested_at") or previous_requested
            updated.append(merged)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        task = dict(task)
        task.setdefault("first_requested_at", task.get("requested_at"))
        updated.append(task)
    return updated