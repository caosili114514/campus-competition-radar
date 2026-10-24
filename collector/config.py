"""信息源配置加载与校验。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .dates import normalize_text
from .schema import SCHEMA_VERSION

PARSER_ALIASES = {
    "html": "html",
    "html_list": "html",
    "html-list": "html",
    "rss": "rss",
    "atom": "atom",
    "json": "json",
    "json_feed": "json",
    "auto": "auto",
}

SOURCE_CONFIG_FIELDS = (
    "id", "name", "domain", "list_url", "parser", "update_frequency",
    "enabled", "source_type", "verified", "verification_note", "is_demo", "url_include_pattern",
    "title_include_keywords", "title_exclude_keywords", "max_items_per_run",
    "max_records", "request_delay_seconds", "items_path",
)

SOURCE_RUNTIME_FIELDS = (
    "last_checked_at", "last_success_at", "status", "result", "failure_reason",
    "records_found", "records_filtered", "records_matched", "records_added",
    "records_updated", "records_duplicates", "robots",
    "effective_request_delay_seconds", "schedule_decision",
    "needs_manual_verification", "http_status",
)


class ConfigError(ValueError):
    pass


def _require_string(source: dict[str, Any], field: str, index: int) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"第 {index + 1} 个来源缺少非空字符串字段 {field}")
    return value.strip()



def _keyword_list(value: Any, field: str, source_id: str) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        values = [str(part).strip() for part in value]
    else:
        raise ConfigError(f"来源 {source_id} 的 {field} 必须是字符串数组")
    return [part for part in values if part]
def normalize_source_config(raw: dict[str, Any], index: int = 0) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError(f"第 {index + 1} 个来源必须是对象")
    source: dict[str, Any] = {}
    source["id"] = _require_string(raw, "id", index)
    if not all(ch.isalnum() or ch in "_-." for ch in source["id"]):
        raise ConfigError(f"来源 id 只能包含字母、数字、下划线、短横线和点: {source['id']}")
    source["name"] = _require_string(raw, "name", index)
    source["domain"] = _require_string(raw, "domain", index).lower()
    source["list_url"] = _require_string(raw, "list_url", index)
    parser = _require_string(raw, "parser", index).lower()
    if parser not in PARSER_ALIASES:
        raise ConfigError(f"来源 {source['id']} 的 parser 不支持: {parser}")
    source["parser"] = PARSER_ALIASES[parser]
    source["update_frequency"] = _require_string(raw, "update_frequency", index)
    source["source_type"] = _require_string(raw, "source_type", index).lower()

    if "enabled" not in raw or not isinstance(raw["enabled"], bool):
        raise ConfigError(f"来源 {source['id']} 的 enabled 必须是布尔值")
    source["enabled"] = raw["enabled"]
    source["verified"] = bool(raw.get("verified", False))
    source["is_demo"] = bool(raw.get("is_demo", False))
    source["verification_note"] = normalize_text(raw.get("verification_note"))
    if source["verified"] and not source["verification_note"]:
        raise ConfigError(f"来源 {source['id']} 声称 verified=true，必须提供 verification_note 证据说明")

    if source["enabled"]:
        parts = urlsplit(source["list_url"])
        if parts.scheme not in ("http", "https", "fixture"):
            raise ConfigError(f"来源 {source['id']} 的 list_url 必须是 http(s) 或 fixture:// 地址")
    try:
        max_records = raw.get("max_records")
        source["max_records"] = int(max_records) if max_records is not None else None
        if source["max_records"] is not None and source["max_records"] < 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"来源 {source['id']} 的 max_records 必须是非负整数") from exc
    try:
        delay = raw.get("request_delay_seconds")
        source["request_delay_seconds"] = float(delay) if delay is not None else None
        if source["request_delay_seconds"] is not None and source["request_delay_seconds"] < 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"来源 {source['id']} 的 request_delay_seconds 必须是非负数") from exc
    source["items_path"] = normalize_text(raw.get("items_path")) or None
    pattern = raw.get("url_include_pattern")
    if pattern is not None:
        pattern = str(pattern).strip() or None
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"来源 {source['id']} 的 url_include_pattern 不是合法正则: {exc}") from exc
    source["url_include_pattern"] = pattern
    source["title_include_keywords"] = _keyword_list(raw.get("title_include_keywords"), "title_include_keywords", source["id"])
    source["title_exclude_keywords"] = _keyword_list(raw.get("title_exclude_keywords"), "title_exclude_keywords", source["id"])
    try:
        max_items = raw.get("max_items_per_run")
        source["max_items_per_run"] = int(max_items) if max_items is not None else None
        if source["max_items_per_run"] is not None and source["max_items_per_run"] < 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"来源 {source['id']} 的 max_items_per_run 必须是非负整数") from exc

    return source
def load_sources_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        raw_sources = data.get("sources")
    elif isinstance(data, list):
        raw_sources = data
    else:
        raise ConfigError("sources 配置顶层必须是对象（含 sources 数组）或数组")
    if not isinstance(raw_sources, list):
        raise ConfigError("sources 配置缺少 sources 数组")
    sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_sources):
        source = normalize_source_config(raw, index)
        if source["id"] in seen_ids:
            raise ConfigError(f"来源 id 重复: {source['id']}")
        seen_ids.add(source["id"])
        sources.append(source)
    return sources


def load_sources(path: str | Path) -> list[dict[str, Any]]:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到 sources 配置文件: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"sources 配置不是合法 JSON: {exc}") from exc
    return load_sources_data(data)


def default_source_state(source: dict[str, Any]) -> dict[str, Any]:
    state = {field: source.get(field) for field in SOURCE_CONFIG_FIELDS}
    state.setdefault("verified", False)
    state.setdefault("is_demo", False)
    state.update({
        "last_checked_at": None,
        "last_success_at": None,
        "status": "disabled" if not source.get("enabled") else "pending",
        "result": "未检查",
        "failure_reason": None,
            "records_found": 0,
        "records_filtered": 0,
        "records_matched": 0,
        "records_added": 0,
        "records_updated": 0,
        "records_duplicates": 0,
        "needs_manual_verification": not bool(source.get("verified", False)),
        "http_status": None,
        "robots": None,
    })
    if not source.get("enabled"):
        state["result"] = "未启用，本次未发起抓取，也未做任何验证"
        state["failure_reason"] = None
    return state


SOURCE_STATUS_LABELS = {
    "disabled": "未启用",
    "pending": "待检查",
    "success": "抓取成功",
    "empty": "抓取成功但无记录",
    "fetch_failed": "抓取失败",
    "parse_failed": "解析失败",
    "config_error": "配置错误",
    "dry_run": "试运行未抓取",
    "robots_blocked": "robots.txt 禁止抓取",
    "not_due": "未到调度周期",
    "manual_skipped": "manual 来源不自动抓取",
}