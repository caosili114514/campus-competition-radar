import unittest

from collector.fetcher import FetchResult
from collector.link_checker import check_link, classify_fetch_result


def result(**overrides):
    data = {"url": "https://example.edu/notice", "final_url": "https://example.edu/notice", "status_code": 200,
            "content_type": "text/html; charset=utf-8", "text": "<html>正常页面正文</html>"}
    data.update(overrides)
    return FetchResult(**data)


class LinkCheckerTests(unittest.TestCase):
    def assert_fact(self, fact, expected):
        self.assertEqual(fact["status"], expected)
        self.assertFalse(fact["registration_open_claim"])
        self.assertIn("不代表报名开放", fact["note"])

    def test_200_is_only_http_fact(self):
        self.assert_fact(classify_fetch_result(result()), "ok")

    def test_redirect(self):
        self.assert_fact(classify_fetch_result(result(status_code=302, final_url="https://example.edu/new")), "redirect")
        self.assert_fact(classify_fetch_result(result(redirected=True, final_url="https://example.edu/new")), "redirect")

    def test_timeout_403_404_connection_and_server_errors(self):
        self.assert_fact(classify_fetch_result(result(status_code=None, timed_out=True, error="请求超时")), "timeout")
        self.assert_fact(classify_fetch_result(result(status_code=403, error=None)), "forbidden")
        self.assert_fact(classify_fetch_result(result(status_code=404, error=None)), "not_found")
        self.assert_fact(classify_fetch_result(result(status_code=None, error="连接失败")), "connection_error")
        self.assert_fact(classify_fetch_result(result(status_code=503, error="HTTP 503")), "server_error")

    def test_js_page_detection(self):
        js = result(text="<html><body><noscript>Please enable JavaScript</noscript><div id='app'></div></body></html>")
        self.assert_fact(classify_fetch_result(js), "js_required_page")

    def test_check_link_handles_invalid_and_fetch_exceptions(self):
        self.assert_fact(check_link("javascript:alert(1)"), "invalid_url")
        class BrokenFetcher:
            def fetch(self, url, headers=None):
                raise TimeoutError("boom")
        self.assert_fact(check_link("https://example.edu/x", BrokenFetcher()), "connection_error")


if __name__ == "__main__":
    unittest.main()