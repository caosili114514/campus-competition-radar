#!/usr/bin/env python3
"""Dependency-free contract checks for generated data and CI logs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

COMPETITION_REQUIRED = [
    "id", "title", "organizer", "category", "competition_level",
    "eligible_participants", "team_size", "registration_start",
    "registration_deadline", "event_start", "event_end", "description",
    "requirements", "official_notice_url", "registration_url", "source_name",
    "source_url", "published_at", "fetched_at", "last_verified_at",
    "verification_status", "registration_status", "confidence", "content_hash",
    "region", "is_demo", "missing_fields", "verification_notes",
]
COMPETITIONS_TOP_REQUIRED = {
    "schema_version", "data_mode", "generated_at", "notice", "record_count", "records",
}
SOURCE_REQUIRED = [
    "id", "name", "source_type", "domain", "list_url", "enabled",
    "update_frequency", "last_checked_at", "last_success_at", "status", "result",
    "failure_reason", "records_found", "records_added",
    "needs_manual_verification", "verified", "is_demo",
]
SOURCES_TOP_REQUIRED = {
    "schema_version", "generated_at", "data_mode", "notice", "source_count",
    "enabled_count", "sources",
}
META_TOP_REQUIRED = {
    "schema_version", "data_mode", "generated_at", "last_run", "summary",
    "run_history", "notice",
}
QUALITY_TOP_REQUIRED = {
    "schema_version", "data_mode", "generated_at", "summary", "summary_text",
    "totals", "verification_status_counts", "registration_status_counts",
    "field_coverage", "missing_field_counts", "link_check_summary",
    "source_summary", "warnings", "notice",
}
REQUIRED_JSON = {
    "competitions.json", "sources.json", "meta.json", "quality-report.json",
}

VERIFICATION_STATUSES = {
    "verified", "pending", "broken", "expired", "incomplete",
}
REGISTRATION_STATUSES = {"open", "upcoming", "closed", "unknown"}
TIME_FIELDS = [
    "registration_start", "registration_deadline", "event_start", "event_end",
    "published_at", "fetched_at", "last_verified_at",
]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

def require_object(value: object, label: str, errors: list[str]) -> dict | None:
    if not isinstance(value, dict):
        errors.append(f"{label}: top-level value must be an object")
        return None
    return value


def require_keys(value: dict, required: set[str] | list[str], label: str, errors: list[str]) -> None:
    missing = sorted(set(required) - set(value))
    if missing:
        errors.append(f"{label}: missing required fields: {', '.join(missing)}")


def check_iso_time(value: object, label: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{label}: expected an ISO-8601 string or null")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label}: invalid ISO-8601 timestamp: {value}")
        return
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        errors.append(f"{label}: timestamp must include the +08:00 offset: {value}")


def load_json_files(data_dir: Path, errors: list[str]) -> dict[str, object]:
    payloads: dict[str, object] = {}
    if not data_dir.is_dir():
        errors.append(f"missing data directory: {data_dir}")
        return payloads

    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        errors.append(f"no JSON files found in {data_dir}")
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payloads[path.name] = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: cannot load JSON: {exc}")
    for filename in sorted(REQUIRED_JSON - set(payloads)):
        errors.append(f"missing or unreadable required file: {data_dir / filename}")
    return payloads


def validate_competitions(payload: object, errors: list[str]) -> list:
    data = require_object(payload, "competitions.json", errors)
    if data is None:
        return []
    require_keys(data, COMPETITIONS_TOP_REQUIRED, "competitions.json", errors)
    if data.get("data_mode") not in {"live", "demo"}:
        errors.append("competitions.json: data_mode must be live or demo")
    check_iso_time(data.get("generated_at"), "competitions.json: generated_at", errors)
    records = data.get("records")
    if not isinstance(records, list):
        errors.append("competitions.json: records must be an array")
        return []

    seen_ids: set[str] = set()
    seen_canonical: set[str] = set()
    seen_titles: set[str] = set()
    seen_source_urls: set[str] = set()
    for index, record in enumerate(records):
        label = f"competitions.json: records[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label}: must be an object")
            continue
        require_keys(record, COMPETITION_REQUIRED, label, errors)
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id.strip():
            errors.append(f"{label}: id must be a non-empty string")
        elif record_id in seen_ids:
            errors.append(f"{label}: duplicate id: {record_id}")
        else:
            seen_ids.add(record_id)

        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label}: title must be a non-empty string")
        else:
            title_key = title.strip().casefold()
            if title_key in seen_titles:
                errors.append(f"{label}: duplicate title: {title}")
            seen_titles.add(title_key)

        canonical_url = record.get("canonical_url")
        if isinstance(canonical_url, str) and canonical_url.strip():
            if canonical_url in seen_canonical:
                errors.append(f"{label}: duplicate canonical_url: {canonical_url}")
            else:
                seen_canonical.add(canonical_url)
        source_url = record.get("source_url")
        if isinstance(source_url, str) and source_url.strip():
            source_url_key = source_url.split("#", 1)[0]
            if source_url_key in seen_source_urls:
                errors.append(f"{label}: duplicate source_url: {source_url_key}")
            else:
                seen_source_urls.add(source_url_key)

        if not isinstance(record.get("is_demo"), bool):
            errors.append(f"{label}: is_demo must be a boolean")
        if not isinstance(record.get("missing_fields"), list):
            errors.append(f"{label}: missing_fields must be an array")
        if record.get("verification_status") not in VERIFICATION_STATUSES:
            errors.append(f"{label}: invalid verification_status")
        if record.get("registration_status") not in REGISTRATION_STATUSES:
            errors.append(f"{label}: invalid registration_status")
        confidence = record.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            errors.append(f"{label}: confidence must be a number between 0 and 1")
        content_hash = record.get("content_hash")
        if content_hash is not None and (
            not isinstance(content_hash, str) or SHA256_RE.fullmatch(content_hash) is None
        ):
            errors.append(f"{label}: content_hash must be 64 lowercase hex characters or null")
        for field in TIME_FIELDS:
            check_iso_time(record.get(field), f"{label}.{field}", errors)

    declared = data.get("record_count")
    if isinstance(declared, int) and declared != len(records):
        errors.append(
            f"competitions.json: record_count {declared} != records length {len(records)}"
        )
    return records

def validate_sources(payload: object, errors: list[str]) -> list:
    data = require_object(payload, "sources.json", errors)
    if data is None:
        return []
    require_keys(data, SOURCES_TOP_REQUIRED, "sources.json", errors)
    if data.get("data_mode") not in {"live", "demo"}:
        errors.append("sources.json: data_mode must be live or demo")
    check_iso_time(data.get("generated_at"), "sources.json: generated_at", errors)
    sources = data.get("sources")
    if not isinstance(sources, list):
        errors.append("sources.json: sources must be an array")
        return []

    seen_ids: set[str] = set()
    for index, source in enumerate(sources):
        label = f"sources.json: sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label}: must be an object")
            continue
        require_keys(source, SOURCE_REQUIRED, label, errors)
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}: id must be a non-empty string")
        elif source_id in seen_ids:
            errors.append(f"{label}: duplicate id: {source_id}")
        else:
            seen_ids.add(source_id)
        for field in ("enabled", "verified", "is_demo", "needs_manual_verification"):
            if not isinstance(source.get(field), bool):
                errors.append(f"{label}: {field} must be a boolean")
        for field in ("last_checked_at", "last_success_at"):
            check_iso_time(source.get(field), f"{label}.{field}", errors)

    declared = data.get("source_count")
    if isinstance(declared, int) and declared != len(sources):
        errors.append(f"sources.json: source_count {declared} != sources length {len(sources)}")
    return sources

def validate_meta_and_quality(
    meta_payload: object,
    quality_payload: object,
    records: list,
    sources: list,
    errors: list[str],
) -> None:
    meta = require_object(meta_payload, "meta.json", errors)
    if meta is not None:
        require_keys(meta, META_TOP_REQUIRED, "meta.json", errors)
        if meta.get("data_mode") not in {"live", "demo"}:
            errors.append("meta.json: data_mode must be live or demo")
        check_iso_time(meta.get("generated_at"), "meta.json: generated_at", errors)
        if not isinstance(meta.get("last_run"), dict):
            errors.append("meta.json: last_run must be an object")
        if not isinstance(meta.get("run_history"), list):
            errors.append("meta.json: run_history must be an array")
        summary = meta.get("summary")
        if isinstance(summary, dict):
            if summary.get("record_count") != len(records):
                errors.append("meta.json: summary.record_count does not match records")
            if summary.get("source_count") != len(sources):
                errors.append("meta.json: summary.source_count does not match sources")
        else:
            errors.append("meta.json: summary must be an object")

    quality = require_object(quality_payload, "quality-report.json", errors)
    if quality is not None:
        require_keys(quality, QUALITY_TOP_REQUIRED, "quality-report.json", errors)
        if quality.get("data_mode") not in {"live", "demo"}:
            errors.append("quality-report.json: data_mode must be live or demo")
        check_iso_time(
            quality.get("generated_at"), "quality-report.json: generated_at", errors
        )

def validate_log(data_dir: Path, errors: list[str]) -> int:
    path = data_dir / "run-log.jsonl"
    if not path.is_file():
        errors.append(f"missing required file: {path}")
        return 0
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{number}: invalid JSONL: {exc}")
                    continue
                if not isinstance(event, dict):
                    errors.append(f"{path}:{number}: each JSONL entry must be an object")
                    continue
                count += 1
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: cannot read JSONL: {exc}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("docs/data"))
    args = parser.parse_args()

    errors: list[str] = []
    payloads = load_json_files(args.data_dir, errors)
    log_count = validate_log(args.data_dir, errors)
    records = validate_competitions(payloads.get("competitions.json"), errors)
    sources = validate_sources(payloads.get("sources.json"), errors)
    validate_meta_and_quality(
        payloads.get("meta.json"), payloads.get("quality-report.json"),
        records, sources, errors,
    )

    if errors:
        print("Data contract validation failed:", file=sys.stderr)
        for issue in errors:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print(
        "Data contract validation passed: "
        f"{len(payloads)} JSON file(s), {len(records)} record(s), "
        f"{len(sources)} source(s), {log_count} log entr(ies)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())