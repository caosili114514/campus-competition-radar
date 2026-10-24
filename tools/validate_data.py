#!/usr/bin/env python3
"""Validate published Campus Competition Radar JSON data.

This validator is intentionally dependency-free so it can run in CI and locally.
It validates structure, ISO-8601 timestamps, enums, content hashes, duplicate
records and the basic consistency of the source and quality reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_RECORD_FIELDS = [
    "id", "title", "organizer", "category", "competition_level",
    "eligible_participants", "team_size", "registration_start",
    "registration_deadline", "event_start", "event_end", "description",
    "requirements", "official_notice_url", "registration_url", "source_name",
    "source_url", "published_at", "fetched_at", "last_verified_at",
    "verification_status", "registration_status", "confidence", "content_hash",
    "region", "is_demo", "missing_fields", "verification_notes",
]
TIME_FIELDS = ["registration_start", "registration_deadline", "event_start", "event_end", "published_at", "fetched_at", "last_verified_at"]
VERIFICATION = {"verified", "pending", "broken", "expired", "incomplete"}
REGISTRATION = {"open", "upcoming", "closed", "unknown"}
CATEGORIES = {"创新创业", "学科竞赛", "设计", "数字媒体", "人工智能", "文化创意", "思政教育", "社会实践", "其他"}
LEVELS = {"国家级", "省级", "校级", "国际级", "其他", "待确认"}
SOURCE_STATUSES = {
    "success", "failed", "skipped", "demo", "partial", "disabled", "pending",
    "empty", "fetch_failed", "parse_failed", "config_error", "dry_run",
    "robots_blocked", "manual_skipped", "not_due",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")

class ValidationError(Exception):
    pass

def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"文件不存在: {path}")
    try:
        with path.open(encoding="utf-8-sig") as fh:
            value = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON 解析失败 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"顶层必须是对象: {path}")
    return value

def check_iso(value: Any, field: str, record_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValidationError(f"{record_id}.{field} 必须是 ISO 字符串或 null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{record_id}.{field} 非法 ISO 时间: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{record_id}.{field} 缺少时区: {value}")

def validate_competitions(path: Path) -> tuple[dict[str, Any], list[str]]:
    data = load_json(path)
    warnings: list[str] = []
    for key in ("schema_version", "data_mode", "generated_at", "records"):
        if key not in data:
            raise ValidationError(f"competitions 缺少顶层字段: {key}")
    if data["data_mode"] not in {"demo", "live"}:
        raise ValidationError("data_mode 必须是 demo 或 live")
    check_iso(data["generated_at"], "generated_at", "root")
    records = data["records"]
    if not isinstance(records, list):
        raise ValidationError("records 必须是数组")
    if data.get("record_count") is not None and data["record_count"] != len(records):
        raise ValidationError("record_count 与实际记录数不一致")
    ids: set[str] = set()
    titles: Counter[str] = Counter()
    urls: Counter[str] = Counter()
    for index, rec in enumerate(records):
        label = rec.get("id") if isinstance(rec, dict) else f"records[{index}]"
        if not isinstance(rec, dict):
            raise ValidationError(f"records[{index}] 必须是对象")
        missing = [key for key in REQUIRED_RECORD_FIELDS if key not in rec]
        if missing:
            raise ValidationError(f"{label} 缺少必需字段: {', '.join(missing)}")
        if not isinstance(rec["id"], str) or not rec["id"].strip():
            raise ValidationError(f"records[{index}].id 必须是非空字符串")
        if rec["id"] in ids:
            raise ValidationError(f"重复 id: {rec['id']}")
        ids.add(rec["id"])
        if not isinstance(rec["title"], str) or not rec["title"].strip():
            raise ValidationError(f"{label}.title 必须是非空字符串")
        if not isinstance(rec["missing_fields"], list) or not all(isinstance(x, str) for x in rec["missing_fields"]):
            raise ValidationError(f"{label}.missing_fields 必须是字符串数组")
        unknown_missing = sorted(set(rec["missing_fields"]) - set(REQUIRED_RECORD_FIELDS))
        if unknown_missing:
            warnings.append(f"{label}.missing_fields 含非标准字段: {unknown_missing}")
        if rec["verification_status"] not in VERIFICATION:
            raise ValidationError(f"{label}.verification_status 非法: {rec['verification_status']}")
        if rec["registration_status"] not in REGISTRATION:
            raise ValidationError(f"{label}.registration_status 非法: {rec['registration_status']}")
        if rec["category"] is not None and rec["category"] not in CATEGORIES:
            warnings.append(f"{label}.category 未使用推荐枚举: {rec['category']}")
        if rec["competition_level"] is not None and rec["competition_level"] not in LEVELS:
            warnings.append(f"{label}.competition_level 未使用推荐枚举: {rec['competition_level']}")
        for field in TIME_FIELDS:
            check_iso(rec[field], field, str(rec["id"]))
        confidence = rec["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValidationError(f"{label}.confidence 必须在 0 到 1 之间")
        if not isinstance(rec["content_hash"], str) or not HEX64.fullmatch(rec["content_hash"]):
            raise ValidationError(f"{label}.content_hash 必须是 64 位小写 sha256")
        if not isinstance(rec["is_demo"], bool):
            raise ValidationError(f"{label}.is_demo 必须是布尔值")
        if data["data_mode"] == "demo" and not rec["is_demo"]:
            raise ValidationError(f"{label} 位于 demo 数据中但 is_demo 不是 true")
        if data["data_mode"] == "live" and rec["is_demo"]:
            warnings.append(f"{label} 标记为演示数据但位于 live 数据集")
        titles[rec["title"].strip().lower()] += 1
        if rec.get("source_url"):
            urls[str(rec["source_url"]).split("#", 1)[0]] += 1
    dup_titles = [title for title, count in titles.items() if count > 1]
    dup_urls = [url for url, count in urls.items() if count > 1]
    if dup_titles:
        raise ValidationError(f"存在重复 title: {dup_titles[:3]}")
    if dup_urls:
        raise ValidationError(f"存在重复 source_url: {dup_urls[:3]}")
    return data, warnings

def validate_sources(path: Path, data_mode: str) -> dict[str, Any]:
    data = load_json(path)
    for key in ("schema_version", "generated_at", "sources"):
        if key not in data:
            raise ValidationError(f"sources 缺少顶层字段: {key}")
    if not isinstance(data["sources"], list):
        raise ValidationError("sources 必须是数组")
    if data.get("source_count") is not None and data["source_count"] != len(data["sources"]):
        raise ValidationError("sources.source_count 与实际来源数不一致")
    if data.get("enabled_count") is not None:
        enabled = sum(1 for s in data["sources"] if isinstance(s, dict) and s.get("enabled") is True)
        if data["enabled_count"] != enabled:
            raise ValidationError("sources.enabled_count 与 enabled=true 来源数不一致")
    ids: set[str] = set()
    for src in data["sources"]:
        if not isinstance(src, dict):
            raise ValidationError("source 条目必须是对象")
        for key in ("id", "name", "source_type", "domain", "list_url", "enabled", "update_frequency", "status", "result", "failure_reason", "records_found", "records_added", "needs_manual_verification"):
            if key not in src:
                raise ValidationError(f"source {src.get('id', '?')} 缺少字段: {key}")
        if src["id"] in ids:
            raise ValidationError(f"重复 source id: {src['id']}")
        ids.add(src["id"])
        if src["status"] not in SOURCE_STATUSES:
            raise ValidationError(f"source {src['id']} status 非法: {src['status']}")
        for key in ("verified", "is_demo", "needs_manual_verification"):
            if key in src and not isinstance(src[key], bool):
                raise ValidationError(f"source {src['id']}.{key} 必须是布尔值")
        for key in ("last_checked_at", "last_success_at"):
            check_iso(src.get(key), key, str(src["id"]))
    if data.get("data_mode") not in {None, data_mode}:
        raise ValidationError("sources.data_mode 与 competitions.data_mode 不一致")
    return data

def validate_meta(path: Path, competitions: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    data = load_json(path)
    for key in ("schema_version", "generated_at", "last_run", "summary", "run_history"):
        if key not in data:
            raise ValidationError(f"meta 缺少顶层字段: {key}")
    check_iso(data["generated_at"], "generated_at", "meta")
    if not isinstance(data["last_run"], dict):
        raise ValidationError("meta.last_run 必须是对象")
    summary = data["summary"]
    if summary.get("record_count") != len(competitions["records"]):
        raise ValidationError("meta.summary.record_count 与实际数据不一致")
    if summary.get("source_count") != len(sources["sources"]):
        raise ValidationError("meta.summary.source_count 与实际信息源数量不一致")
    return data

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验赛讯雷达 JSON 数据质量")
    parser.add_argument("--data-dir", default="docs/data", help="包含 competitions.json 等文件的目录")
    parser.add_argument("--allow-live-demo", action="store_true", help="允许 live 数据包含演示记录（会警告）")
    args = parser.parse_args(argv)
    base = Path(args.data_dir)
    try:
        competitions, warnings = validate_competitions(base / "competitions.json")
        sources = validate_sources(base / "sources.json", competitions["data_mode"])
        meta = validate_meta(base / "meta.json", competitions, sources)
        quality_path = base / "quality-report.json"
        if quality_path.exists():
            quality = load_json(quality_path)
            if quality.get("record_count") not in (None, len(competitions["records"])):
                warnings.append("quality-report.record_count 与 competitions 不一致")
            quality_summary = quality.get("totals")
            if isinstance(quality_summary, dict):
                if quality_summary.get("record_count") not in (None, len(competitions["records"])):
                    warnings.append("quality-report.totals.record_count 与 competitions 不一致")
            for key in ("summary", "totals", "verification_status_counts", "registration_status_counts", "field_coverage", "missing_field_counts", "link_check_summary", "source_summary", "warnings", "notice"):
                if key not in quality:
                    warnings.append(f"quality-report 缺少指标: {key}")
        print(f"[OK] competitions: {len(competitions['records'])} 条记录，模式={competitions['data_mode']}")
        print(f"[OK] sources: {len(sources['sources'])} 个来源；meta 数据一致")
        print("[OK] 必需字段、ISO 时区、枚举、content_hash、重复 id/title/source_url 检查通过")
        for warning in warnings:
            print(f"[WARN] {warning}")
        return 0
    except ValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
