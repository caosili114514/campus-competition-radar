"""严格的数据结构、字段补全与校验。

字段契约来自项目 Lead：所有键始终存在；未知值为 null；数组字段为空数组。
日期统一为带 +08:00 的 ISO8601。采集成功不等同于信息已验证。
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any

from .dates import (
    REGISTRATION_STATUS_LABELS,
    TZ,
    derive_registration_status,
    parse_datetime,
    TZ_NAME,
)

SCHEMA_VERSION = "1.0.0"
DATA_NOTICE = (
    "本文件由校园竞赛雷达采集框架生成。默认信息源与记录均未经人工验证；"
    "链接可访问只代表当时的 HTTP 事实，不代表报名开放、资格有效或主办方确认。"
)

VERIFICATION_STATUSES = ("verified", "pending", "broken", "expired", "incomplete")
REGISTRATION_STATUSES = ("open", "upcoming", "closed", "unknown")
SOURCE_TYPES = ("official", "university", "college", "media", "manual", "fixture", "other")

COMPETITION_FIELDS = (
    "id",
    "title",
    "organizer",
    "category",
    "competition_level",
    "eligible_participants",
    "team_size",
    "registration_start",
    "registration_deadline",
    "event_start",
    "event_end",
    "description",
    "requirements",
    "official_notice_url",
    "registration_url",
    "source_name",
    "source_url",
    "published_at",
    "fetched_at",
    "last_verified_at",
    "verification_status",
    "registration_status",
    "confidence",
    "content_hash",
    "region",
    "is_demo",
    "missing_fields",
    "verification_notes",
    "source_id",
    "source_type",
    "canonical_url",
    "verification_history",
    "change_history",
    "link_check",
    "registration_link_check",
    "detail_fetch",
    "source_list_url",
)

DATE_FIELDS = (
    "registration_start",
    "registration_deadline",
    "event_start",
    "event_end",
    "published_at",
    "fetched_at",
    "last_verified_at",
)

MISSING_FIELD_CANDIDATES = (
    "organizer",
    "category",
    "competition_level",
    "eligible_participants",
    "team_size",
    "registration_start",
    "registration_deadline",
    "event_start",
    "event_end",
    "description",
    "requirements",
    "official_notice_url",
    "registration_url",
    "published_at",
    "region",
)

STRING_FIELDS = (
    "id", "title", "organizer", "category", "competition_level",
    "eligible_participants", "team_size", "description", "requirements",
    "official_notice_url", "registration_url", "source_name", "source_url",
    "region", "source_id", "source_type", "canonical_url", "content_hash", "source_list_url",
)

ARRAY_FIELDS = ("missing_fields", "verification_history", "change_history")

CONTENT_HASH_FIELDS = (
    "title", "organizer", "category", "competition_level",
    "eligible_participants", "team_size", "registration_start",
    "registration_deadline", "event_start", "event_end", "description",
    "requirements", "region",
)


def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat(timespec="seconds")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = "；".join(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return text or None


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, number)), 2)


def compute_record_content_hash(record: dict[str, Any]) -> str:
    """对稳定的赛事内容字段做 sha256，不含抓取时间或链接检查时间。"""
    payload = {field: record.get(field) for field in CONTENT_HASH_FIELDS}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def blank_competition_record() -> dict[str, Any]:
    """返回含有全部约定键的空记录，未知字段为 null。"""
    record: dict[str, Any] = {field: None for field in COMPETITION_FIELDS}
    record.update({
        "is_demo": False,
        "verification_status": "pending",
        "registration_status": "unknown",
        "confidence": 0.0,
        "missing_fields": [],
        "verification_history": [],
        "change_history": [],
        "link_check": None,
    })
    return record
def _normalize_date_field(field: str, value: Any) -> str | None:
    if field in ("registration_deadline", "event_end"):
        return parse_datetime(value, end_of_day=True)
    return parse_datetime(value, end_of_day=False)


def _estimate_confidence(record: dict[str, Any]) -> float:
    """依据可提取信息完整度估算 0-1 置信度；不代表官方核实。"""
    present = 0
    for field in MISSING_FIELD_CANDIDATES:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            present += 1
        elif value is not None:
            present += 1
    coverage = present / len(MISSING_FIELD_CANDIDATES) if MISSING_FIELD_CANDIDATES else 0.0
    base = 0.2 if record.get("title") else 0.0
    return round(min(0.95, base + 0.75 * coverage), 2)
def normalize_competition_record(record: dict[str, Any] | None, *,
                                 now: str | datetime | None = None,
                                 source: dict[str, Any] | None = None) -> dict[str, Any]:
    """补全键、规范化日期/枚举/数组并动态推导报名状态。"""
    data = dict(record or {})
    normalized = blank_competition_record()

    for field in STRING_FIELDS:
        normalized[field] = _clean_text(data.get(field))

    for field in DATE_FIELDS:
        normalized[field] = _normalize_date_field(field, data.get(field))

    ver_status = str(data.get("verification_status") or "pending").strip()
    if ver_status not in VERIFICATION_STATUSES:
        ver_status = "pending"
    normalized["verification_status"] = ver_status
    normalized["is_demo"] = bool(data.get("is_demo", False))
    normalized["confidence"] = _clamp_confidence(data.get("confidence"))

    normalized["verification_notes"] = _clean_text(data.get("verification_notes"))
    for field in ARRAY_FIELDS:
        value = data.get(field)
        normalized[field] = list(value) if isinstance(value, (list, tuple)) else []
    link_check = data.get("link_check")
    normalized["link_check"] = dict(link_check) if isinstance(link_check, dict) else None
    registration_link_check = data.get("registration_link_check")
    normalized["registration_link_check"] = dict(registration_link_check) if isinstance(registration_link_check, dict) else None
    detail_fetch = data.get("detail_fetch")
    normalized["detail_fetch"] = dict(detail_fetch) if isinstance(detail_fetch, dict) else None

    source_defaults = source or {}
    if not normalized["source_id"]:
        normalized["source_id"] = _clean_text(source_defaults.get("id"))
    if not normalized["source_name"]:
        normalized["source_name"] = _clean_text(source_defaults.get("name"))
    if not normalized["source_list_url"]:
        normalized["source_list_url"] = _clean_text(source_defaults.get("list_url"))
    if not normalized["source_type"]:
        normalized["source_type"] = _clean_text(source_defaults.get("source_type"))
    if normalized["source_url"] and normalized["source_url"] == normalized["source_list_url"]:
        normalized["source_url"] = None
    if not normalized["fetched_at"]:
        normalized["fetched_at"] = now_iso() if now is None else parse_datetime(now)
    if normalized["fetched_at"] is None:
        normalized["fetched_at"] = now_iso()
    normalized["registration_status"] = derive_registration_status(
        normalized["registration_start"], normalized["registration_deadline"]
    )
    normalized["missing_fields"] = [
        field for field in MISSING_FIELD_CANDIDATES
        if normalized.get(field) is None or (
            isinstance(normalized.get(field), str) and not str(normalized.get(field)).strip()
        )
    ]
    if normalized["confidence"] <= 0:
        normalized["confidence"] = _estimate_confidence(normalized)
    if normalized["verification_status"] != "verified" and normalized["last_verified_at"]:
        normalized["last_verified_at"] = None
    normalized["content_hash"] = compute_record_content_hash(normalized)
    if not normalized["id"]:
        normalized["id"] = make_record_id(
            normalized["source_id"] or "",
            normalized["canonical_url"] or normalized["official_notice_url"],
            normalized["title"] or "",
        )
    return normalized
def make_record_id(source_id: str, url: str | None, title: str) -> str:
    basis = f"{source_id.strip()}|{(url or '').strip()}|{title.strip()}"
    return "comp_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def validate_competition_record(record: dict[str, Any]) -> list[str]:
    """返回中文校验错误列表；空列表代表符合记录契约。"""
    errors: list[str] = []
    missing_keys = [key for key in COMPETITION_FIELDS if key not in record]
    if missing_keys:
        errors.append("缺少字段: " + ", ".join(missing_keys))
    if not record.get("id"):
        errors.append("id 不能为空")
    if not record.get("title"):
        errors.append("title 不能为空")
    if record.get("verification_status") not in VERIFICATION_STATUSES:
        errors.append("verification_status 枚举非法")
    if record.get("registration_status") not in REGISTRATION_STATUSES:
        errors.append("registration_status 枚举非法")
    if not isinstance(record.get("is_demo"), bool):
        errors.append("is_demo 必须是布尔值")
    if not isinstance(record.get("missing_fields"), list):
        errors.append("missing_fields 必须是数组")
    try:
        confidence = float(record.get("confidence"))
        if not 0 <= confidence <= 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("confidence 必须是 0-1 数字")
    for field in DATE_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not re.match(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$", value):
            errors.append(f"{field} 必须是 +08:00 ISO8601 或 null")
    hash_value = record.get("content_hash")
    if hash_value is not None and not re.fullmatch(r"[0-9a-f]{64}", str(hash_value)):
        errors.append("content_hash 必须是 sha256 十六进制")
    for field in STRING_FIELDS:
        if record.get(field) is not None and not isinstance(record.get(field), str):
            errors.append(f"{field} 必须是字符串或 null")
    return errors


def build_competitions_document(records: list[dict[str, Any]], *,
                                generated_at: str | None = None,
                                data_mode: str = "live") -> dict[str, Any]:
    normalized = [normalize_competition_record(record) for record in records]
    return {
        "schema_version": SCHEMA_VERSION,
        "data_mode": data_mode,
        "generated_at": generated_at or now_iso(),
        "notice": DATA_NOTICE,
        "record_count": len(normalized),
        "records": normalized,
    }