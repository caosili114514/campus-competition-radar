import unittest

from collector.dedupe import (
    canonicalize_url,
    merge_incoming,
    records_are_similar,
    text_similarity,
)
from collector.schema import normalize_competition_record


def make_record(**overrides):
    data = {
        "source_id": "src",
        "source_name": "测试来源",
        "source_url": "https://example.edu/list",
        "title": "关于举办2026年全国大学生数学建模竞赛的通知",
        "organizer": "中国工业与应用数学学会",
        "category": "数学建模",
        "registration_start": "2026-03-01T00:00:00+08:00",
        "registration_deadline": "2026-04-30T23:59:59+08:00",
        "description": "测试正文",
        "official_notice_url": "https://example.edu/notice/1?utm_source=a",
        "canonical_url": "https://example.edu/notice/1",
    }
    data.update(overrides)
    return normalize_competition_record(data, now="2026-10-24T20:56:20+08:00")


class DedupeTests(unittest.TestCase):
    def test_url_canonicalization_removes_tracking_and_fragment(self):
        url = canonicalize_url("HTTPS://Example.COM/a/?utm_source=x&b=2&a=1#section")
        self.assertEqual(url, "https://example.com/a?a=1&b=2")

    def test_url_duplicate_merges_and_preserves_history(self):
        existing = make_record(description="旧正文")
        incoming = make_record(description="新正文")
        result = merge_incoming([existing], [incoming], now="2026-10-25T09:00:00+08:00")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.added, 0)
        self.assertEqual(result.updated, 1)
        merged = result.records[0]
        self.assertEqual(merged["id"], existing["id"])
        self.assertEqual(merged["description"], "新正文")
        self.assertEqual(merged["verification_status"], "pending")
        self.assertIsNone(merged["last_verified_at"])
        self.assertTrue(merged["change_history"])
        self.assertEqual(merged["change_history"][-1]["event"], "content_changed_pending_verification")

    def test_title_and_organizer_similarity_dedupes_despite_different_urls(self):
        first = make_record(
            title="关于举办2026年全国大学生数学建模竞赛的通知",
            official_notice_url="https://example.edu/notice/a",
            canonical_url="https://example.edu/notice/a",
        )
        second = make_record(
            title="2026年全国大学生数学建模竞赛",
            official_notice_url="https://example.edu/notice/b",
            canonical_url="https://example.edu/notice/b",
        )
        self.assertGreaterEqual(text_similarity(first["title"], second["title"]), 0.9)
        self.assertTrue(records_are_similar(first, second))
        result = merge_incoming([first], [second], now="2026-10-25T09:00:00+08:00")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.added, 0)

    def test_max_new_limits_new_records_but_never_drops_history(self):
        existing = make_record(official_notice_url="https://example.edu/old", canonical_url="https://example.edu/old")
        new_one = make_record(title="全新程序设计竞赛", official_notice_url="https://example.edu/new1", canonical_url="https://example.edu/new1")
        new_two = make_record(title="全新电子设计竞赛", official_notice_url="https://example.edu/new2", canonical_url="https://example.edu/new2")
        result = merge_incoming([existing], [new_one, new_two], now="2026-10-25T09:00:00+08:00", max_new=1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.added, 1)
        self.assertEqual(result.skipped_due_to_limit, 1)


if __name__ == "__main__":
    unittest.main()