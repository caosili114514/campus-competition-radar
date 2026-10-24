"""Lead integration checks for the checked-in demo dataset and source policy."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from collector.extractors import extract_eligible_participants, extract_team_size

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs" / "data"
REQUIRED = {
    "id", "title", "organizer", "category", "competition_level",
    "eligible_participants", "team_size", "registration_start",
    "registration_deadline", "event_start", "event_end", "description",
    "requirements", "official_notice_url", "registration_url", "source_name",
    "source_url", "published_at", "fetched_at", "last_verified_at",
    "verification_status", "registration_status", "confidence",
    "content_hash", "region", "is_demo", "missing_fields", "verification_notes",
}


class PublishedDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.competitions = json.loads((DATA / "competitions.json").read_text(encoding="utf-8-sig"))
        cls.sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8-sig"))
        cls.meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8-sig"))
        cls.quality = json.loads((DATA / "quality-report.json").read_text(encoding="utf-8-sig"))

    def test_every_published_demo_record_is_marked_and_has_contract_fields(self):
        self.assertEqual(self.competitions["data_mode"], "demo")
        self.assertTrue(self.competitions["records"])
        for record in self.competitions["records"]:
            self.assertTrue(REQUIRED.issubset(record), record.get("id"))
            self.assertIs(record["is_demo"], True)
            self.assertIn("【模拟】", record["title"])
            self.assertNotEqual(record["content_hash"], "0" * 64)


    def test_demo_links_and_organizers_cannot_be_mistaken_for_real_events(self):
        for record in self.competitions["records"]:
            self.assertIn("演示", record["organizer"])
            for field in ("official_notice_url", "registration_url", "source_url"):
                value = record.get(field)
                if value:
                    host = (urlsplit(value).hostname or "").lower()
                    self.assertIn(host, {"example.com", "example.invalid"}, f"{record['id']}.{field}")
            self.assertIn("演示", record["verification_notes"])

    def test_demo_reports_and_counts_are_consistent(self):
        records = self.competitions["records"]
        self.assertEqual(len(records), self.competitions["record_count"])
        self.assertEqual(self.meta["summary"]["record_count"], len(records))
        self.assertEqual(self.meta["summary"]["source_count"], len(self.sources["sources"]))
        self.assertEqual(self.quality["totals"]["record_count"], len(records))
        for source in self.sources["sources"]:
            self.assertIsInstance(source["needs_manual_verification"], bool)

    def test_real_candidate_sources_are_disabled_and_unverified(self):
        config = json.loads((ROOT / "collector" / "sources.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(len(config["sources"]), 6)
        for source in config["sources"]:
            self.assertIs(source["enabled"], False, source["id"])
            self.assertIs(source["verified"], False, source["id"])
            self.assertTrue(source["list_url"].startswith(("http://", "https://")))
            self.assertTrue(source.get("verification_note"))
        self.assertNotIn("cpipc.acge.org.cn", {s["domain"] for s in config["sources"]})


class ExtractorPolicyTests(unittest.TestCase):
    def test_team_size_never_mistakes_teacher_count_for_students(self):
        self.assertIsNone(extract_team_size("每队可配备不超过2名指导教师"))
        self.assertEqual(extract_team_size("每队3名学生，1-2名指导教师"), "3人")
        self.assertEqual(extract_team_size("3人一队"), "3人")
        self.assertEqual(
            extract_team_size("每个参赛队由同一所院校的 2~9 名全日制本科生组成"),
            "2-9人",
        )

    def test_eligibility_only_uses_visible_explicit_phrases(self):
        self.assertEqual(
            extract_eligible_participants("参赛队成员为全日制在校本科或高职高专学生"),
            "全日制在校本科",
        )
        self.assertIsNone(extract_eligible_participants("欢迎感兴趣的同学关注后续消息"))

    def test_eligibility_does_not_capture_facing_scenario_or_teacher_training(self):
        self.assertIsNone(extract_eligible_participants("面向城市内涝预警的智能监测网络等实际应用场景"))
        self.assertIsNone(extract_eligible_participants("面向各省级赛区承办负责人开展了业务培训"))
        self.assertEqual(
            extract_eligible_participants("大赛是面向普通高校本科生的赛事之一"),
            "普通高校本科生",
        )


if __name__ == "__main__":
    unittest.main()
