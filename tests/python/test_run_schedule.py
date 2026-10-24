import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from collector.dates import TZ
from collector.fetcher import FetchResult
from collector.run import RunOptions, run_collection

FIXED = datetime(2026, 10, 24, 21, 0, tzinfo=TZ)


class DelayFetcher:
    def __init__(self):
        self.request_delay = 1.0
        self.calls = []

    def set_request_delay(self, seconds):
        self.request_delay = seconds

    def fetch(self, url, headers=None):
        self.calls.append(url)
        text = "<html><body><p>没有候选链接</p></body></html>"
        return FetchResult(url=url, final_url=url, status_code=200, text=text,
                           body=text.encode("utf-8"), content_type="text/html; charset=utf-8")


def write_sources(path, sources):
    path.write_text(json.dumps({"schema_version": "1.0.0", "sources": sources}, ensure_ascii=False), encoding="utf-8")


def source(source_id, *, delay=2.0, frequency="daily"):
    return {
        "id": source_id, "name": source_id, "domain": "example.edu",
        "list_url": f"https://{source_id}.example/list", "parser": "html",
        "update_frequency": frequency, "enabled": True,
        "source_type": "official_candidate", "verified": False, "is_demo": False,
        "max_items_per_run": 10, "request_delay_seconds": delay,
    }
class ScheduleAndDelayTests(unittest.TestCase):
    def test_source_request_delay_takes_max_of_global_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source("delay", delay=7.0)])
            fake = DelayFetcher()
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=False, max_records=10, request_delay=2.0),
                fetcher=fake, clock=lambda: FIXED,
            )
            self.assertEqual(fake.request_delay, 7.0)
            self.assertEqual(outcome.sources[0]["effective_request_delay_seconds"], 7.0)
            self.assertTrue(any(log["event"] == "source_request_delay" for log in outcome.logs))

    def test_weekly_recent_and_manual_sources_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "out"
            output.mkdir()
            sources = root / "sources.json"
            write_sources(sources, [
                source("weekly", frequency="weekly"),
                source("manual", frequency="manual"),
            ])
            previous = {
                "schema_version": "1.0.0",
                "sources": [
                    {"id": "weekly", "last_success_at": (FIXED - timedelta(days=1)).isoformat()},
                    {"id": "manual", "last_success_at": None},
                ],
            }
            (output / "sources.json").write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
            fake = DelayFetcher()
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=False, max_records=10, request_delay=1.0),
                fetcher=fake, clock=lambda: FIXED,
            )
            self.assertEqual(fake.calls, [])
            statuses = {state["id"]: state["status"] for state in outcome.sources}
            self.assertEqual(statuses["weekly"], "not_due")
            self.assertEqual(statuses["manual"], "manual_skipped")
            self.assertEqual(outcome.status, "skipped")
            self.assertEqual(outcome.meta["summary"]["skipped_count"], 2)
            weekly_state = next(state for state in outcome.sources if state["id"] == "weekly")
            self.assertEqual(weekly_state["last_success_at"], (FIXED - timedelta(days=1)).isoformat())

    def test_force_allows_manual_source_to_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source("manual", frequency="manual")])
            fake = DelayFetcher()
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=False, max_records=10, force=True),
                fetcher=fake, clock=lambda: FIXED,
            )
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(outcome.sources[0]["status"], "empty")


if __name__ == "__main__":
    unittest.main()