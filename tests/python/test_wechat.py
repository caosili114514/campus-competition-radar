import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from collector.dates import TZ
from collector.fetcher import FetchResult
from collector.wechat import process_wechat_url

NOW = datetime(2026, 10, 24, 21, 0, tzinfo=TZ)
URL = "https://mp.weixin.qq.com/s/example"


class FakeFetcher:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def fetch(self, url, headers=None):
        self.calls.append(url)
        return self.result


def response(html, status=200):
    return FetchResult(url=URL, final_url=URL, status_code=status, text=html,
                       body=html.encode("utf-8"), content_type="text/html; charset=utf-8")


class WechatTests(unittest.TestCase):
    def test_public_article_success_is_still_pending_verification(self):
        html = """<html><head><meta property="og:title" content="2026年程序设计竞赛通知">
        <meta property="article:published_time" content="2026-10-20T09:00:00+08:00"></head>
        <body><nav>首页 登录</nav><div class="rich_media_content" id="js_content">
        <p>主办单位：测试大学。</p><p>参赛对象：全日制在校大学生，每队1-3人。</p>
        <p>报名时间：2026年11月1日至2026年11月30日。</p>
        <p>作品要求：提交源代码与说明文档。</p></div></body></html>"""
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            outcome = process_wechat_url(
                URL, output, fetcher=FakeFetcher(response(html)),
                respect_robots=False, now=NOW,
            )
            self.assertEqual(outcome.status, "success_pending_verification")
            comp = json.loads((output / "competitions.json").read_text(encoding="utf-8"))
            self.assertEqual(comp["data_mode"], "live")
            self.assertEqual(len(comp["records"]), 1)
            record = comp["records"][0]
            self.assertEqual(record["verification_status"], "pending")
            self.assertIsNone(record["last_verified_at"])
            self.assertEqual(record["team_size"], "1-3人")
            self.assertEqual(record["registration_deadline"], "2026-11-30T23:59:59+08:00")
            self.assertTrue((output / "manual-pending.json").exists())

    def test_403_creates_pending_task_without_bypass(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            outcome = process_wechat_url(
                URL, output, fetcher=FakeFetcher(response("", status=403)),
                respect_robots=False, now=NOW,
            )
            self.assertEqual(outcome.status, "pending_manual_review")
            pending = json.loads((output / "manual-pending.json").read_text(encoding="utf-8"))
            task = pending["tasks"][0]
            self.assertEqual(task["status"], "pending_manual_review")
            self.assertTrue(task["no_login_bypass"])
            self.assertEqual(task["http_status"], 403)
            self.assertFalse((output / "competitions.json").exists())

    def test_captcha_or_verification_page_goes_to_pending(self):
        html = """<html><body><div id="js_content">环境异常，请完成验证后访问。</div></body></html>"""
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            outcome = process_wechat_url(
                URL, output, fetcher=FakeFetcher(response(html)),
                respect_robots=False, now=NOW,
            )
            self.assertEqual(outcome.status, "pending_manual_review")
            self.assertIn("未绕过", outcome.message)
            pending = json.loads((output / "manual-pending.json").read_text(encoding="utf-8"))
            self.assertTrue(pending["tasks"][0]["no_login_bypass"])


if __name__ == "__main__":
    unittest.main()