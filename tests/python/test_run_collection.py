import contextlib
import io
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from collector.cli import main as cli_main
from collector.dates import TZ
from collector.fetcher import FetchResult
from collector.run import RunOptions, apply_source_filters, run_collection
from collector.schema import COMPETITION_FIELDS

FIXED = datetime(2026, 10, 24, 21, 0, 0, tzinfo=TZ)


def fetch_result(url, *, status=200, text="", content_type="text/html; charset=utf-8", error=None, timed_out=False):
    return FetchResult(
        url=url, final_url=url, status_code=status, text=text, body=text.encode("utf-8"),
        content_type=content_type, error=error, timed_out=timed_out,
    )


class FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch(self, url, headers=None):
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            return fetch_result(url, status=404)
        return response


def write_sources(path: Path, sources):
    path.write_text(json.dumps({"schema_version": "1.0.0", "sources": sources}, ensure_ascii=False), encoding="utf-8")


def source_config(source_id, list_url, **extra):
    data = {
        "id": source_id,
        "name": source_id + " 来源",
        "domain": "example.edu",
        "list_url": list_url,
        "parser": "html",
        "update_frequency": "daily",
        "enabled": True,
        "source_type": "fixture",
        "verified": False,
        "is_demo": False,
        "max_items_per_run": 10,
    }
    data.update(extra)
    return data
class FixtureDetailTests(unittest.TestCase):
    def test_detail_body_is_used_and_detail_failure_is_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixtures = root / "fixtures"
            output = root / "out"
            fixtures.mkdir()
            (fixtures / "list.html").write_text("""
            <html><body><ul>
              <li><a href="fixture://detail-ok.html">关于举办2026年全国大学生数学建模竞赛的通知</a></li>
              <li><a href="fixture://missing.html">程序设计竞赛报名通知</a></li>
            </ul></body></html>""", encoding="utf-8")
            (fixtures / "detail-ok.html").write_text("""
            <html><head><meta property="og:title" content="详情标题">
            <meta property="article:published_time" content="2026-10-20T09:00:00+08:00"></head>
            <body><nav>首页 登录</nav><div class="article-content">
            <h1>关于举办2026年全国大学生数学建模竞赛的通知</h1>
            <p>主办单位：中国工业与应用数学学会。</p>
            <p>参赛对象：全日制在校大学生。每队1-3人。</p>
            <p>报名时间：2026年11月1日至2026年11月30日。</p>
            <p>作品要求：提交论文与代码。</p></div><footer>版权</footer></body></html>""", encoding="utf-8")
            sources = root / "sources.json"
            write_sources(sources, [source_config(
                "fixture", "fixture://list.html", title_include_keywords=["竞赛"],
                url_include_pattern=r"detail-ok|missing",
            )])
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False, max_records=10,
                           fixtures_dir=fixtures),
                clock=lambda: FIXED,
            )
            self.assertEqual(outcome.status, "success")
            self.assertEqual(len(outcome.records), 2)
            self.assertEqual(outcome.sources[0]["detail_fetch_attempted"], 2)
            self.assertEqual(outcome.sources[0]["detail_fetch_failed"], 1)
            success_record = next(r for r in outcome.records if "数学建模" in r["title"])
            self.assertEqual(success_record["organizer"], "中国工业与应用数学学会")
            self.assertEqual(success_record["registration_deadline"], "2026-11-30T23:59:59+08:00")
            self.assertIn("提交论文与代码", success_record["requirements"])
            self.assertEqual(success_record["official_notice_url"], "fixture://detail-ok.html")
            self.assertEqual(success_record["source_url"], "fixture://detail-ok.html")
            self.assertEqual(success_record["source_list_url"], "fixture://list.html")
            self.assertEqual(success_record["detail_fetch"]["status"], "ok")
            failed_record = next(r for r in outcome.records if "程序设计" in r["title"])
            self.assertTrue(failed_record["detail_fetch"]["error"])
            self.assertIsNone(failed_record["registration_deadline"])
            self.assertTrue((output / "competitions.json").exists())
            self.assertTrue((output / "sources.json").exists())
            self.assertTrue((output / "meta.json").exists())
            self.assertTrue((output / "quality-report.json").exists())
            self.assertTrue((output / "run-log.jsonl").exists())
            comp = json.loads((output / "competitions.json").read_text(encoding="utf-8"))
            self.assertEqual(comp["data_mode"], "live")
            self.assertEqual(comp["record_count"], 2)
            for record in comp["records"]:
                self.assertEqual(set(COMPETITION_FIELDS).issubset(record.keys()), True)
                self.assertFalse(record["is_demo"])
                self.assertEqual(record["verification_status"], "pending")
    def test_one_source_failure_does_not_stop_other_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "out"
            sources = root / "sources.json"
            write_sources(sources, [
                source_config("bad", "https://bad.example/list"),
                source_config("good", "https://good.example/list",
                              title_include_keywords=["竞赛"]),
            ])
            good_list = """<ul><li><a href="https://good.example/detail/1">程序设计竞赛报名通知</a></li></ul>"""
            good_detail = """<div class="article-content"><h1>程序设计竞赛报名通知</h1>
            <p>主办单位：测试大学。报名时间：2026年11月1日至2026年11月20日。</p></div>"""
            fake = FakeFetcher({
                "https://bad.example/list": fetch_result("https://bad.example/list", status=500, error="HTTP 500"),
                "https://good.example/list": fetch_result("https://good.example/list", text=good_list),
                "https://good.example/detail/1": fetch_result("https://good.example/detail/1", text=good_detail),
            })
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=False, max_records=10),
                fetcher=fake, clock=lambda: FIXED,
            )
            statuses = {state["id"]: state["status"] for state in outcome.sources}
            self.assertEqual(statuses["bad"], "fetch_failed")
            self.assertEqual(statuses["good"], "success")
            self.assertEqual(outcome.status, "partial_failure")
            self.assertEqual(len(outcome.records), 1)
            self.assertEqual(outcome.records[0]["organizer"], "测试大学")
            self.assertEqual(outcome.records[0]["official_notice_url"], "https://good.example/detail/1")

    def test_robots_disallow_blocks_source_without_fetching_list(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source_config("blocked", "https://blocked.example/news")])
            fake = FakeFetcher({
                "https://blocked.example/robots.txt": fetch_result(
                    "https://blocked.example/robots.txt",
                    text="User-agent: *\nDisallow: /\n",
                ),
            })
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=True, max_records=10),
                fetcher=fake, clock=lambda: FIXED,
            )
            self.assertEqual(outcome.sources[0]["status"], "robots_blocked")
            self.assertIn("Disallow", outcome.sources[0]["failure_reason"])
            self.assertNotIn("https://blocked.example/news", fake.calls)
            self.assertEqual(len(outcome.records), 0)
    def test_existing_live_history_is_merged_and_demo_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "out"
            output.mkdir()
            sources = root / "sources.json"
            write_sources(sources, [source_config("history", "https://history.example/list")])
            old_doc = {
                "schema_version": "1.0.0", "data_mode": "live", "generated_at": "2026-10-20T00:00:00+08:00",
                "notice": "old", "records": [
                    {"title": "旧程序设计竞赛通知", "id": "comp_old", "is_demo": False,
                     "official_notice_url": "https://history.example/detail/old",
                     "source_id": "history", "source_name": "history 来源",
                     "source_url": "https://history.example/list", "verification_status": "pending",
                     "registration_deadline": "2026-12-31"},
                    {"title": "演示记录", "is_demo": True},
                ],
            }
            (output / "competitions.json").write_text(json.dumps(old_doc, ensure_ascii=False), encoding="utf-8")
            fake = FakeFetcher({
                "https://history.example/list": fetch_result(
                    "https://history.example/list",
                    text='<ul><li><a href="https://history.example/detail/new">电子设计竞赛通知</a></li></ul>',
                ),
                "https://history.example/detail/new": fetch_result(
                    "https://history.example/detail/new",
                    text='<div class="article-content"><p>主办单位：历史大学。</p></div>',
                ),
            })
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=False,
                           respect_robots=False, max_records=10),
                fetcher=fake, clock=lambda: FIXED,
            )
            self.assertEqual(len(outcome.records), 2)
            self.assertTrue(any(record["id"] == "comp_old" for record in outcome.records))
            self.assertFalse(any(record["title"] == "演示记录" for record in outcome.records))

    def test_filters_and_cli_default_empty_and_dry_run(self):
        items = [
            {"title": "程序设计竞赛通知", "url": "https://example.edu/news/1"},
            {"title": "招聘公告", "url": "https://example.edu/news/2"},
            {"title": "数学建模竞赛", "url": "https://example.edu/other/3"},
            {"title": "计算机设计大赛获奖公告", "url": "https://example.edu/news/4"},
        ]
        filtered, filtered_count, matched = apply_source_filters(items, {
            "url_include_pattern": r"/news/\d+",
            "title_include_keywords": ["竞赛"],
            "title_exclude_keywords": ["招聘", "获奖"],
            "max_items_per_run": 1,
        })
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered_count, 3)
        self.assertEqual(matched, 1)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources-disabled.json"
            write_sources(sources, [source_config(
                "disabled-source", "https://disabled.example/list", enabled=False,
            )])
            output = root / "out"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli_main([
                    "--sources", str(sources), "--output", str(output),
                    "--max-records", "5",
                ])
            self.assertEqual(code, 0)
            comp = json.loads((output / "competitions.json").read_text(encoding="utf-8"))
            self.assertEqual(comp["records"], [])
            self.assertEqual(comp["data_mode"], "live")
            meta = json.loads((output / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["last_run"]["status"], "no_enabled_sources")
            raw = (output / "competitions.json").read_text(encoding="utf-8")
            self.assertNotIn("\\u", raw)
            self.assertFalse(any("docs" in path.lower() and "data" in path.lower() for path in [str(output)]))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources-disabled.json"
            write_sources(sources, [source_config(
                "disabled-source", "https://disabled.example/list", enabled=False,
            )])
            output = root / "must-not-exist"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli_main(["--sources", str(sources),
                                 "--output", str(output), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertFalse(output.exists())
if __name__ == "__main__":
    unittest.main()
