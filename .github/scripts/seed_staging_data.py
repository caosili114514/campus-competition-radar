#!/usr/bin/env python3
"""Seed a collector staging directory with existing live history and source schedule state."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

HISTORY_FILES = ("competitions.json", "sources.json", "meta.json", "run-log.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("docs/data"))
    parser.add_argument("--stage", type=Path, default=Path("collector-output"))
    args = parser.parse_args()

    args.stage.mkdir(parents=True, exist_ok=True)
    competitions = args.target / "competitions.json"
    if not competitions.is_file():
        print("No existing competitions.json; staging starts empty.")
        return 0

    try:
        with competitions.open("r", encoding="utf-8-sig") as handle:
            data_mode = json.load(handle).get("data_mode")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot inspect existing competitions.json: {exc}") from exc

    if data_mode != "live":
        print(
            f"Existing data_mode is {data_mode!r}, not live; "
            "staging starts empty and demo records are not injected as history."
        )
        return 0

    copied: list[str] = []
    for name in HISTORY_FILES:
        source = args.target / name
        if source.is_file():
            shutil.copy2(source, args.stage / name)
            copied.append(name)
    print(
        "Seeded staging with existing live history and run log: "
        + ", ".join(copied or ["(no history files found)"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())