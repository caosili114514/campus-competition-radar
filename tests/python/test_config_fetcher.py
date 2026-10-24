from pathlib import Path
import tempfile
import unittest

from collector.config import ConfigError, load_sources, normalize_source_config
from collector.fetcher import FixtureFetcher, decode_body


class ConfigTests(unittest.TestCase):
    def test_source_filters_and_aliases_are_normalized(self):
        source = normalize_source_config({
            "id": "candidate", "name": "候选来源", "domain": "example.edu",
            "list_url": "https://example.edu/news", "parser": "html_list",
            "update_frequency": "daily", "enabled": False,
            "source_type": "official_candidate", "verified": False,
            "url_include_pattern": r"/info/\d+", "title_include_keywords": "竞赛,大赛",
            "title_exclude_keywords": ["招聘"], "max_items_per_run": 12,
        })
        self.assertEqual(source["parser"], "html")
        self.assertEqual(source["title_include_keywords"], ["竞赛", "大赛"])
        self.assertEqual(source["max_items_per_run"], 12)

    def test_verified_true_requires_evidence_note(self):
        with self.assertRaises(ConfigError):
            normalize_source_config({
                "id": "x", "name": "X", "domain": "example.edu",
                "list_url": "https://example.edu/", "parser": "html",
                "update_frequency": "daily", "enabled": True,
                "source_type": "official", "verified": True,
            })

    def test_default_candidates_are_disabled_and_unverified(self):
        sources = load_sources("collector/sources.json")
        self.assertEqual(len(sources), 6)
        self.assertTrue(all(source["enabled"] is False for source in sources))
        self.assertTrue(all(source["verified"] is False for source in sources))
        self.assertTrue(all(source["url_include_pattern"] for source in sources))


class FetcherTests(unittest.TestCase):
    def test_fixture_fetcher_reads_only_fixture_scheme_inside_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "page.html").write_text("<html>中文</html>", encoding="utf-8")
            fetcher = FixtureFetcher(root)
            result = fetcher.fetch("fixture://page.html")
            self.assertTrue(result.ok)
            self.assertIn("中文", result.text)
            self.assertIsNotNone(fetcher.fetch("https://example.edu/page.html").error)
            self.assertIsNotNone(fetcher.fetch("fixture://../outside.html").error)

    def test_decode_body_detects_gbk_meta_charset(self):
        body = '<meta charset="gbk"><p>中文正文</p>'.encode("gbk")
        text = decode_body(body, "text/html")
        self.assertIn("中文正文", text)


if __name__ == "__main__":
    unittest.main()