import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from collector.dates import TZ
from collector.fetcher import FetchResult
from collector.run import RunOptions, run_collection

FIXED = datetime(2026, 10, 24, 21, 0, tzinfo=TZ)


def payload(url, text="", status=200):
    return FetchResult(url=url, final_url=url, status_code=status, text=text,
                       body=text.encode("utf-8"), content_type="text/html; charset=utf-8")


class FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch(self, url, headers=None):
        self.calls.append(url)
        return self.responses.get(url, payload(url, status=404))


def write_sources(path, sources):
    path.write_text(json.dumps({"schema_version": "1.0.0", "sources": sources}, ensure_ascii=False), encoding="utf-8")


def source(source_id, list_url):
    return {
        "id": source_id, "name": source_id, "domain": "example.edu", "list_url": list_url,
        "parser": "html", "update_frequency": "daily", "enabled": True,
        "source_type": "official_candidate", "verified": False, "is_demo": False,
        "max_items_per_run": 10,
    }
class LinkCheckRunTests(unittest.TestCase):
    def test_notice_and_registration_links_are_checked_and_saved_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source("links", "https://links.example/list")])
            detail = """<div class="article-content"><h1>链接测试竞赛通知</h1>
            <p>报名时间：2026年11月1日至2026年11月20日。</p>
            <p>报名入口：https://links.example/signup</p></div>"""
            fake = FakeFetcher({
                "https://links.example/list": payload("https://links.example/list",
                    '<ul><li><a href="https://links.example/detail/1">链接测试竞赛通知</a></li></ul>'),
                "https://links.example/detail/1": payload("https://links.example/detail/1", detail),
            })
            calls = []
            def linker(url):
                calls.append(url)
                not_found = url.endswith("/signup")
                return {"url": url, "status": "not_found" if not_found else "ok",
                        "status_label": "HTTP 404 未找到" if not_found else "HTTP 可达",
                        "http_status": 404 if not_found else 200, "final_url": url,
                        "redirected": False, "js_page_detected": False, "error": None,
                        "registration_open_claim": False, "note": "仅 HTTP 事实"}
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=True,
                           respect_robots=False, max_records=10),
                fetcher=fake, link_check_func=linker, clock=lambda: FIXED,
            )
            self.assertEqual(len(calls), 2)
            record = outcome.records[0]
            self.assertEqual(record["link_check"]["status"], "ok")
            self.assertEqual(record["registration_link_check"]["status"], "not_found")
            self.assertEqual(record["verification_status"], "broken")
            self.assertIn("报名链接", record["verification_notes"])
            quality = json.loads((output / "quality-report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["totals"]["links_checked"], 2)
            self.assertEqual(quality["registration_link_check_summary"]["not_found"], 1)
    def test_max_link_checks_caps_notice_plus_registration_total(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source("links2", "https://links2.example/list")])
            list_html = """<ul>
            <li><a href="https://links2.example/d1">第一场程序设计竞赛通知</a></li>
            <li><a href="https://links2.example/d2">第二场电子设计竞赛通知</a></li></ul>"""
            detail = """<div class="article-content"><p>报名时间：2026年11月1日至2026年11月20日。</p>
            <p>报名入口：https://links2.example/signup</p></div>"""
            fake = FakeFetcher({
                "https://links2.example/list": payload("https://links2.example/list", list_html),
                "https://links2.example/d1": payload("https://links2.example/d1", detail),
                "https://links2.example/d2": payload("https://links2.example/d2", detail),
            })
            calls = []
            def linker(url):
                calls.append(url)
                return {"url": url, "status": "ok", "status_label": "HTTP 可达",
                        "http_status": 200, "final_url": url, "redirected": False,
                        "js_page_detected": False, "error": None,
                        "registration_open_claim": False, "note": "仅 HTTP 事实"}
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=True,
                           link_check_limit=2, respect_robots=False, max_records=10),
                fetcher=fake, link_check_func=linker, clock=lambda: FIXED,
            )
            self.assertEqual(len(calls), 2)
            quality = json.loads((output / "quality-report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["totals"]["links_checked"], 2)


    def test_registration_js_page_keeps_pending_and_notes_fact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources.json"
            output = root / "out"
            write_sources(sources, [source("links3", "https://links3.example/list")])
            detail = """<div class="article-content"><h1>JS 报名页竞赛通知</h1>
            <p>报名入口：https://links3.example/signup</p></div>"""
            fake = FakeFetcher({
                "https://links3.example/list": payload("https://links3.example/list",
                    '<ul><li><a href="https://links3.example/detail/1">JS 报名页竞赛通知</a></li></ul>'),
                "https://links3.example/detail/1": payload("https://links3.example/detail/1", detail),
            })
            def linker(url):
                status = "js_required_page" if url.endswith("/signup") else "ok"
                return {"url": url, "status": status,
                        "status_label": "疑似需 JavaScript 渲染" if status != "ok" else "HTTP 可达",
                        "http_status": 200, "final_url": url, "redirected": False,
                        "js_page_detected": status != "ok", "error": None,
                        "registration_open_claim": False, "note": "仅 HTTP 事实"}
            outcome = run_collection(
                RunOptions(sources_path=sources, output_dir=output, check_links=True,
                           respect_robots=False, max_records=10),
                fetcher=fake, link_check_func=linker, clock=lambda: FIXED,
            )
            record = outcome.records[0]
            self.assertEqual(record["registration_link_check"]["status"], "js_required_page")
            self.assertEqual(record["verification_status"], "pending")
            self.assertIn("报名链接", record["verification_notes"])
            self.assertIn("JavaScript", record["verification_notes"])

if __name__ == "__main__":
    unittest.main()