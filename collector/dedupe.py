"""URL/内容/标题相似度去重与历史合并。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import difflib
import re
import unicodedata
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .schema import compute_record_content_hash, normalize_competition_record

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "source", "ref", "referrer", "share", "share_token",
    "fbclid", "gclid", "yclid", "clickid", "_ga",
}

TITLE_NOISE_RE = re.compile(
    r"^(?:关于)?(?:举办|开展|组织|举行|发布)?|"
    r"(?:的通知|通知|公告|公示|报名通知|活动通知|新闻)$"
)


def _normalize_unicode(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def canonicalize_url(url: str | None) -> str | None:
    """规范化 URL，用于去重；保留路径语义，移除常见追踪参数。"""
    if not url:
        return None
    text = _normalize_unicode(url)
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))


def normalize_title(title: str | None) -> str:
    text = _normalize_unicode(title)
    text = re.sub(r"20\d{2}\s*年?", "", text)
    text = TITLE_NOISE_RE.sub("", text)
    text = re.sub(r"[\s\u3000·•:：,，。.!！?？【】\[\]（）()”\"'《》<>—–\-_/\\]+", "", text)
    return text.lower()


def text_similarity(left: str | None, right: str | None) -> float:
    a = normalize_title(left)
    b = normalize_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter, longer = sorted((len(a), len(b)))
        return 0.9 + 0.1 * shorter / longer
    return difflib.SequenceMatcher(None, a, b).ratio()


def organizer_similarity(left: str | None, right: str | None) -> float | None:
    a = re.sub(r"[\s\u3000,，。.;；]", "", _normalize_unicode(left)).lower()
    b = re.sub(r"[\s\u3000,，。.;；]", "", _normalize_unicode(right)).lower()
    if not a or not b:
        return None
    if a == b or a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()
def record_url(record: dict[str, Any]) -> str | None:
    return canonicalize_url(
        record.get("canonical_url") or record.get("official_notice_url")
    )


def records_are_similar(left: dict[str, Any], right: dict[str, Any], *,
                        title_threshold: float = 0.9) -> bool:
    """标题+主办方相似度判断；未知主办方时阈值更严格。"""
    left_url = record_url(left)
    right_url = record_url(right)
    if left_url and right_url and left_url == right_url:
        return True
    if left.get("content_hash") and left.get("content_hash") == right.get("content_hash"):
        return True

    title_score = text_similarity(left.get("title"), right.get("title"))
    organizer_score = organizer_similarity(left.get("organizer"), right.get("organizer"))
    if organizer_score is None:
        return title_score >= max(0.94, title_threshold + 0.04)
    if organizer_score >= 0.88:
        return title_score >= title_threshold
    if organizer_score < 0.5:
        return title_score >= 0.97
    return title_score >= 0.94


def find_duplicate_index(incoming: dict[str, Any], records: list[dict[str, Any]]) -> int | None:
    incoming_url = record_url(incoming)
    if incoming_url:
        for index, record in enumerate(records):
            if record_url(record) == incoming_url:
                return index
    incoming_hash = incoming.get("content_hash")
    if incoming_hash:
        for index, record in enumerate(records):
            if record.get("content_hash") == incoming_hash:
                return index
    for index, record in enumerate(records):
        if records_are_similar(incoming, record):
            return index
    return None


def _content_change_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> list[str]:
    fields = (
        "title", "organizer", "category", "competition_level",
        "eligible_participants", "team_size", "registration_start",
        "registration_deadline", "event_start", "event_end", "description",
        "requirements", "region",
    )
    return [field for field in fields if incoming.get(field) is not None and incoming.get(field) != existing.get(field)]


def merge_record(existing: dict[str, Any], incoming: dict[str, Any], *,
                 now: str) -> tuple[dict[str, Any], bool, list[str]]:
    """合并同一条记录；内容变化时触发人工待核验，不静默覆盖历史。"""
    old_record = deepcopy(existing)
    merged = deepcopy(existing)
    changed_fields = _content_change_fields(existing, incoming)
    old_hash = existing.get("content_hash")
    new_hash = incoming.get("content_hash") or compute_record_content_hash(incoming)

    for field in (
        "title", "organizer", "category", "competition_level",
        "eligible_participants", "team_size", "registration_start",
        "registration_deadline", "event_start", "event_end", "description",
        "requirements", "region", "published_at",
    ):
        if incoming.get(field) is not None:
            merged[field] = incoming[field]
    if incoming.get("registration_url"):
        # 只接受来源中明确给出的报名 URL，绝不猜测。
        merged["registration_url"] = incoming["registration_url"]
    if incoming.get("official_notice_url") and not merged.get("official_notice_url"):
        merged["official_notice_url"] = incoming["official_notice_url"]

    merged["fetched_at"] = now
    merged["source_id"] = existing.get("source_id") or incoming.get("source_id")
    merged["source_name"] = existing.get("source_name") or incoming.get("source_name")
    existing_source_url = existing.get("source_url")
    incoming_source_url = incoming.get("source_url")
    if incoming_source_url and (
        not existing_source_url
        or existing_source_url == existing.get("source_list_url")
        or existing_source_url == incoming.get("source_list_url")
    ):
        merged["source_url"] = incoming_source_url
    else:
        merged["source_url"] = existing_source_url or incoming_source_url
    merged["source_list_url"] = (
        existing.get("source_list_url") or incoming.get("source_list_url")
    )
    merged["source_type"] = existing.get("source_type") or incoming.get("source_type")
    merged["canonical_url"] = existing.get("canonical_url") or incoming.get("canonical_url")
    if incoming.get("link_check") is not None:
        merged["link_check"] = incoming["link_check"]
    if incoming.get("registration_link_check") is not None:
        merged["registration_link_check"] = incoming["registration_link_check"]
    if incoming.get("detail_fetch") is not None:
        merged["detail_fetch"] = incoming["detail_fetch"]

    if changed_fields or (old_hash and new_hash and old_hash != new_hash):
        history = list(merged.get("change_history") or [])
        history.append({
            "changed_at": now,
            "event": "content_changed_pending_verification",
            "fields": changed_fields,
            "previous_content_hash": old_hash,
            "new_content_hash": new_hash,
            "note": "来源内容发生变化，已保留旧记录信息摘要并标记待人工核验。",
        })
        merged["change_history"] = history[-20:]
        merged["verification_status"] = "pending"
        merged["last_verified_at"] = None
        merged["verification_notes"] = "来源内容发生变化，需人工复核后再确认。"
        merged["confidence"] = min(float(merged.get("confidence") or 0), float(incoming.get("confidence") or 0))
        updated = True
    else:
        merged["confidence"] = max(float(merged.get("confidence") or 0), float(incoming.get("confidence") or 0))
        updated = False
        # 页面 404/失效属于可核实的公开链接事实。
        if (incoming.get("link_check") or {}).get("status") == "not_found":
            merged["verification_status"] = "broken"
            merged["verification_notes"] = "公开通知链接返回 404；不代表赛事本身不存在。"

    merged["content_hash"] = new_hash
    normalized = normalize_competition_record(merged, now=now)
    # normalize 默认重算状态可能覆盖 broken/pending；以合并结论为准，但保留合法枚举。
    if merged.get("verification_status") in ("pending", "broken", "incomplete", "verified"):
        normalized["verification_status"] = merged["verification_status"]
    if normalized["verification_status"] != "verified":
        normalized["last_verified_at"] = None
    return normalized, updated, changed_fields
@dataclass
class MergeResult:
    records: list[dict[str, Any]]
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    content_changed: int = 0
    skipped_due_to_limit: int = 0
    stats_by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def stats_for(self, source_id: str) -> dict[str, int]:
        return self.stats_by_source.setdefault(source_id, {
            "found": 0,
            "added": 0,
            "updated": 0,
            "unchanged": 0,
            "content_changed": 0,
            "skipped": 0,
        })


def merge_incoming(existing: Iterable[dict[str, Any]], incoming: Iterable[dict[str, Any]], *,
                   now: str, max_new: int | None = None) -> MergeResult:
    """把本次采集合并进历史；max_new 只限制新增，绝不删除历史。"""
    records = [normalize_competition_record(record) for record in existing]
    result = MergeResult(records=records)
    added_count = 0

    for raw_incoming in incoming:
        item = normalize_competition_record(raw_incoming, now=now)
        source_id = str(item.get("source_id") or "")
        source_stats = result.stats_for(source_id)
        source_stats["found"] += 1
        index = find_duplicate_index(item, records)
        if index is None:
            if max_new is not None and added_count >= max_new:
                result.skipped_due_to_limit += 1
                source_stats["skipped"] += 1
                continue
            records.append(item)
            added_count += 1
            result.added += 1
            source_stats["added"] += 1
            continue

        merged, changed, changed_fields = merge_record(records[index], item, now=now)
        records[index] = merged
        if changed:
            result.updated += 1
            source_stats["updated"] += 1
            result.content_changed += 1
            source_stats["content_changed"] += 1
        else:
            result.unchanged += 1
            source_stats["unchanged"] += 1
    return result


def dedupe_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """对单批记录内部去重，保留已有记录并合并后出现记录。"""
    result = merge_incoming([], records).records
    return result