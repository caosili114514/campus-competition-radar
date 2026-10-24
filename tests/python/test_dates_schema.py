import json
from datetime import datetime
import unittest

from collector.dates import (
    TZ,
    derive_registration_status,
    find_periods,
    parse_datetime,
    parse_registration_deadline,
    parse_registration_period,
)
from collector.schema import (
    COMPETITION_FIELDS,
    blank_competition_record,
    build_competitions_document,
    normalize_competition_record,
    validate_competition_record,
)


class DateTests(unittest.TestCase):
    def test_chinese_datetime_has_plus_08(self):
        value = parse_datetime("2026年10月24日 20:56")
        self.assertEqual(value, "2026-10-24T20:56:00+08:00")

    def test_iso_and_rfc_are_converted_to_plus_08(self):
        self.assertEqual(parse_datetime("2026-10-24T12:56:20Z"), "2026-10-24T20:56:20+08:00")
        self.assertEqual(parse_datetime("Sat, 24 Oct 2026 20:56:20 +0800"), "2026-10-24T20:56:20+08:00")

    def test_date_range_and_deadline_end_of_day(self):
        periods = find_periods("报名时间：2026年3月1日-4月30日")
        self.assertEqual(periods[0]["start"], "2026-03-01T00:00:00+08:00")
        self.assertEqual(periods[0]["end"], "2026-04-30T23:59:59+08:00")
        self.assertEqual(parse_registration_deadline("报名截止：2026年4月30日"),
                         "2026-04-30T23:59:59+08:00")
        start, end = parse_registration_period("报名时间：2026年3月1日至2026年4月30日")
        self.assertTrue(start.endswith("+08:00"))
        self.assertTrue(end.endswith("+08:00"))

    def test_deadline_uses_first_date_after_label_not_signature_date(self):
        text = "发布者: 时间:2026-06-24 浏览: 报名截止时间(即2026年6月30日08:00,以系统时间为准) 秘书处 2026年6月24日"
        self.assertEqual(parse_registration_deadline(text), "2026-06-30T08:00:00+08:00")

    def test_generic_cutoff_is_not_assumed_to_be_registration_deadline(self):
        self.assertIsNone(parse_registration_deadline("作品上传截止时间：2026年6月30日"))
    def test_deadline_status_is_dynamic(self):
        now = datetime(2026, 3, 15, 10, 0, tzinfo=TZ)
        self.assertEqual(derive_registration_status("2026-03-01T00:00:00+08:00", "2026-03-31T23:59:59+08:00", now=now), "open")
        self.assertEqual(derive_registration_status("2026-04-01T00:00:00+08:00", "2026-04-30T23:59:59+08:00", now=now), "upcoming")
        self.assertEqual(derive_registration_status("2026-01-01T00:00:00+08:00", "2026-02-01T23:59:59+08:00", now=now), "closed")
        self.assertEqual(derive_registration_status(None, None, now=now), "unknown")


class SchemaTests(unittest.TestCase):
    def test_all_contract_keys_always_exist(self):
        record = blank_competition_record()
        self.assertEqual(set(record), set(COMPETITION_FIELDS))
        for field in COMPETITION_FIELDS:
            self.assertIn(field, record)
        self.assertIsNone(record["organizer"])
        self.assertEqual(record["missing_fields"], [])

    def test_missing_fields_are_reported_and_dates_normalized(self):
        record = normalize_competition_record({
            "title": "只包含标题的竞赛",
            "registration_deadline": "2026-12-31",
            "source_id": "src",
            "source_name": "来源",
            "source_url": "https://example.edu/list",
        })
        self.assertIn("organizer", record["missing_fields"])
        self.assertIn("registration_url", record["missing_fields"])
        self.assertEqual(record["registration_deadline"], "2026-12-31T23:59:59+08:00")
        self.assertTrue(record["content_hash"])
        self.assertEqual(len(record["content_hash"]), 64)
        self.assertEqual(validate_competition_record(record), [])

    def test_document_is_utf8_and_has_top_contract(self):
        record = normalize_competition_record({
            "title": "中文赛事", "organizer": "测试大学", "source_id": "s",
            "source_name": "来源", "source_url": "https://example.edu/list",
        })
        doc = build_competitions_document([record])
        self.assertEqual(doc["schema_version"], "1.0.0")
        self.assertIn("notice", doc)
        self.assertEqual(doc["records"][0]["title"], "中文赛事")
        raw = json.dumps(doc, ensure_ascii=False)
        self.assertNotIn("\\u", raw)


if __name__ == "__main__":
    unittest.main()