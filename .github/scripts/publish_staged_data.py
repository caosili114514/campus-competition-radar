#!/usr/bin/env python3
"""Safely publish collector staging data into docs/data.

Default sources are disabled. A no-enabled-source run, or an empty run while
the checked-in site still contains demo data, must not replace the demo data.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

PUBLISH_FILES = (
    "competitions.json",
    "sources.json",
    "meta.json",
    "quality-report.json",
    "run-log.jsonl",
)
OPTIONAL_FILES = ("run-history.json",)


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: top-level value must be an object")
    return value


def enabled_source_count(config_path: Path) -> int:
    config = load_json(config_path)
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise SystemExit(f"{config_path}: sources must be an array")
    return sum(
        1 for source in sources
        if isinstance(source, dict) and source.get("enabled") is True
    )


def set_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("collector/sources.json"))
    parser.add_argument("--stage", type=Path, default=Path("collector-output"))
    parser.add_argument("--target", type=Path, default=Path("docs/data"))
    args = parser.parse_args()

    enabled = enabled_source_count(args.sources)
    meta = load_json(args.stage / "meta.json")
    last_run = meta.get("last_run") if isinstance(meta.get("last_run"), dict) else {}
    run_status = str(last_run.get("status") or meta.get("collection_status") or "unknown")
    run_message = str(last_run.get("message") or meta.get("notice") or "")
    print(f"[INFO] enabled sources: {enabled}")
    print(f"[INFO] staged run status: {run_status}")
    if run_message:
        print(f"[INFO] staged run message: {run_message}")

    if enabled == 0:
        print(
            "[SKIP] No source has enabled=true. Keeping docs/data unchanged "
            "(including any demo data); staging is for diagnostics only."
        )
        set_output("published", "false")
        set_output("reason", "no_enabled_sources")
        return 0

    missing = [name for name in PUBLISH_FILES if not (args.stage / name).is_file()]
    if missing:
        raise SystemExit(f"staging output is incomplete: missing {', '.join(missing)}")

    competitions = load_json(args.stage / "competitions.json")
    records = competitions.get("records")
    if not isinstance(records, list):
        raise SystemExit("staged competitions.json records must be an array")
    declared_count = competitions.get("record_count")
    staged_count = declared_count if isinstance(declared_count, int) else len(records)

    target_mode = None
    target_competitions = args.target / "competitions.json"
    if target_competitions.is_file():
        target_mode = load_json(target_competitions).get("data_mode")

    if staged_count == 0 and target_mode == "demo":
        print(
            "[SKIP] Staged run produced 0 records and docs/data is still demo data. "
            "Refusing to replace demo data with an empty live dataset."
        )
        set_output("published", "false")
        set_output("reason", "empty_stage_preserves_demo")
        return 0

    args.target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in PUBLISH_FILES:
        shutil.copy2(args.stage / name, args.target / name)
        copied.append(name)
    for name in OPTIONAL_FILES:
        source = args.stage / name
        if source.is_file():
            shutil.copy2(source, args.target / name)
            copied.append(name)

    print(
        f"[PUBLISH] Staged run has {staged_count} record(s), target mode was "
        f"{target_mode or 'missing'}; copied: {', '.join(copied)}"
    )
    set_output("published", "true")
    set_output("reason", "staged_data_published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())