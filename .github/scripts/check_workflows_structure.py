#!/usr/bin/env python3
"""Conservative structural checks for workflow files without PyYAML.

This is not a YAML parser. GitHub's own workflow parser is authoritative.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    "update-data.yml": [
        "name:",
        "on:",
        "  schedule:",
        "    - cron: '17 18 * * *'",
        "  workflow_dispatch:",
        "permissions:",
        "  contents: write",
        "concurrency:",
        "  group: update-competition-data",
        "  cancel-in-progress: false",
        "jobs:",
        "    runs-on: ubuntu-latest",
        "uses: actions/checkout@v4",
        "uses: actions/setup-python@v5",
        "python-version: '3.12'",
        "python -m unittest discover -s tests/python -v",
        "node --version",
        "npm test",
        "          rm -rf collector-output",
        "python .github/scripts/seed_staging_data.py --target docs/data --stage collector-output",
        "python -m collector --sources collector/sources.json --output collector-output",
        "python .github/scripts/validate_data.py --data-dir collector-output",
        "python .github/scripts/publish_staged_data.py --sources collector/sources.json --stage collector-output --target docs/data",
        "python .github/scripts/validate_data.py --data-dir docs/data",
        "if: steps.publish.outputs.published == 'true'",
        "git add docs/data",
        "git commit -m ",
        "git pull --rebase --autostash",
        "git push origin ",
    ],
    "deploy-pages.yml": [
        "name:",
        "on:",
        "  push:",
        "    branches:",
        "      - main",
        "  workflow_dispatch:",
        "  workflow_run:",
        "      - Update competition data",
        "    types:",
        "      - completed",
        "permissions:",
        "  contents: read",
        "  pages: write",
        "  id-token: write",
        "concurrency:",
        "  group: github-pages",
        "  cancel-in-progress: false",
        "    environment:",
        "      name: github-pages",
        "uses: actions/configure-pages@v5",
        "uses: actions/upload-pages-artifact@v3",
        "          path: '.'",
        "uses: actions/deploy-pages@v4",
        "touch .nojekyll",
        "rm -rf .git node_modules",
    ],
}

REQUIRED_TOP_LEVEL = {"name", "on", "permissions", "concurrency", "jobs"}
EXPECTED_PATHS = [
    "'index.html'",
    "'assets/**'",
    "'docs/data/**'",
    "'collector/**'",
    "'.github/workflows/deploy-pages.yml'",
]


def main() -> int:
    errors: list[str] = []
    for filename, expected_fragments in WORKFLOWS.items():
        path = ROOT / ".github" / "workflows" / filename
        if not path.is_file():
            errors.append(f"missing workflow: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        if "\t" in text:
            errors.append(f"{filename}: contains a tab character")
        for number, line in enumerate(lines, start=1):
            if line != line.rstrip():
                errors.append(f"{filename}:{number}: trailing whitespace")

        top_level: list[str] = []
        for line in lines:
            if not line or line.startswith((" ", "#")):
                continue
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)", line)
            if match:
                top_level.append(match.group(1))
        duplicates = sorted({key for key in top_level if top_level.count(key) > 1})
        if duplicates:
            errors.append(f"{filename}: duplicate top-level keys: {duplicates}")
        missing_top = sorted(REQUIRED_TOP_LEVEL - set(top_level))
        if missing_top:
            errors.append(f"{filename}: missing top-level keys: {missing_top}")

        for fragment in expected_fragments:
            if fragment not in text:
                errors.append(f"{filename}: missing expected fragment: {fragment!r}")
        if "--output docs/data" in text:
            errors.append(f"{filename}: collector must not write directly to docs/data")
        if " --force" in text or re.search(r"git push[^\n]*\s-f(?:\s|$)", text):
            errors.append(f"{filename}: must not contain a force push")

        actions = re.findall(r"uses:\s*([^\s#]+)", text)
        if not actions:
            errors.append(f"{filename}: no action uses found")
        for action in actions:
            if "@" not in action:
                errors.append(f"{filename}: action is not pinned to a ref: {action}")

    deploy = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    for expected_path in EXPECTED_PATHS:
        if expected_path not in deploy:
            errors.append(f"deploy-pages.yml: missing push path {expected_path}")
    if "workflow_run:\n" not in deploy:
        errors.append("deploy-pages.yml: workflow_run block should start at top level")
    if "workflow_run:" in deploy and "Update competition data" not in deploy:
        errors.append("deploy-pages.yml: workflow_run does not reference the update workflow name")

    if errors:
        print("Workflow structural checks FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Workflow structural checks passed (2 files; YAML parser not available).")
    print("This is not a full YAML parse; rely on GitHub Actions for authoritative validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())