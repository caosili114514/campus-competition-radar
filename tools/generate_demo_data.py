from __future__ import annotations
import hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data"
FIX = ROOT / "tests" / "fixtures"
TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 24, 20, 55, 27, tzinfo=TZ)

def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None

def dt(day: int, hour: int = 9, month: int = 10, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=TZ)

BASE = {
    "category": "创新创业", "competition_level": "国家级", "region": "全国",
    "eligible_participants": "普通高校全日制在校本科生、研究生",
    "team_size": "3–5 人", "event_start": None, "event_end": None,
    "description": "此条记录为项目内置演示夹具，仅用于验证界面、筛选和状态计算，不是真实赛事，也不构成报名建议。",
    "requirements": "模拟要求：提交项目说明、展示材料与演示视频；具体要求请以真实官方通知为准。",
    "source_name": "演示信息源（合成，非真实来源）", "source_type": "demo",
    "source_url": "https://example.com/demo-fixture",
    "official_notice_url": "https://example.com/demo-fixture", "registration_url": None,
    "published_at": iso(dt(20, 10)), "fetched_at": iso(dt(24, 20)),
    "last_verified_at": None, "verification_status": "pending", "confidence": 0.55,
    "is_demo": True, "missing_fields": [],
    "verification_notes": "演示记录：未访问或核验任何真实赛事网站；状态仅用于功能展示。",
    "verification_history": [{"checked_at": iso(dt(24, 20)), "status": "pending", "method": "demo_fixture", "note": "内置演示数据，未进行网络核验。", "http_status": None}],
    "change_history": [],
}

def r(**kw):
    x = json.loads(json.dumps(BASE, ensure_ascii=False))
    x.update(kw)
    return x

RECORDS = []
RECORDS += [
r(id="demo-001", title="【模拟】全国大学生创新实践挑战赛",
  organizer="演示主办方 · 某高校创新创业学院（非真实机构）",
  category="创新创业", competition_level="国家级",
  eligible_participants="普通高校全日制本科生、研究生", team_size="3–5 人",
  registration_start=iso(dt(1)), registration_deadline=iso(datetime(2026,10,29,23,59,59,tzinfo=TZ)),
  event_start=iso(dt(15, 9, 11)), event_end=iso(dt(17, 18, 11)),
  description="【演示数据】用于展示正在报名、即将截止的创新创业类竞赛详情，不可据此报名。",
  requirements="模拟提交材料：项目计划书、路演视频、团队简历；作品须为原创。",
  registration_url="https://example.com/demo-register-001", verification_status="verified",
  confidence=0.82, verification_notes="演示记录：模拟已核验状态，便于展示核验徽标；未访问真实赛事网站。"),
]
RECORDS += [
r(id="demo-002", title="【模拟】AI 创意应用设计大赛",
  organizer="演示主办方 · 人工智能教育联盟（非真实机构）",
  category="人工智能", competition_level="省级",
  eligible_participants="省内高校在校生，专业不限", team_size="1–4 人",
  registration_start=iso(dt(1, 9, 11)), registration_deadline=iso(datetime(2026,11,20,23,59,59,tzinfo=TZ)),
  event_start=iso(dt(5, 9, 12)), event_end=iso(dt(6, 18, 12)),
  description="【演示数据】用于展示报名尚未开始的赛事及日期推导，不是真实 AI 比赛。",
  requirements="模拟要求：围绕大学生学习场景设计 AI 应用原型，提交说明文档与演示。",
  registration_url="https://example.com/demo-register-002", verification_status="verified",
  confidence=0.78, verification_notes="演示记录：模拟已核验状态，不代表真实赛事。"),
r(id="demo-003", title="【模拟】高校数字媒体作品征集赛",
  organizer="演示主办方 · 数字创意学院（非真实机构）",
  category="数字媒体", competition_level="校级",
  eligible_participants="全校本科生", team_size="1–3 人",
  registration_start=iso(dt(10)), registration_deadline=iso(datetime(2026,10,31,23,59,59,tzinfo=TZ)),
  description="【演示数据】展示 7 天内截止的短周期赛事信息，不是真实作品征集。",
  requirements="模拟要求：提交不超过 3 分钟的数字短片或交互作品说明。",
  verification_status="pending", confidence=0.61,
  verification_notes="演示记录：报名入口缺失；展示待确认和 7 天内截止效果。",
  missing_fields=["registration_url"]),
]
RECORDS += [
r(id="demo-004", title="【模拟】往届大学生设计创新赛",
  organizer="演示主办方 · 创意设计协会（非真实机构）",
  category="设计", competition_level="省级",
  eligible_participants="省内高校在校生", team_size="2–4 人",
  registration_start=iso(dt(1, 9, 8)), registration_deadline=iso(datetime(2026,9,30,23,59,59,tzinfo=TZ)),
  event_start=iso(dt(15, 9, 10)), event_end=iso(dt(18, 18, 10)),
  description="【演示数据】一个报名已截止的历史记录，用于验证截止状态覆盖逻辑。",
  requirements="模拟要求：提交作品集和设计说明，不接收逾期材料。",
  registration_url="https://example.com/demo-register-004", verification_status="expired",
  confidence=0.73, verification_notes="演示记录：模拟已截止状态，未核验真实页面。"),
r(id="demo-005", title="【模拟】大学生跨学科知识挑战赛",
  organizer="演示主办方 · 通识教育中心（非真实机构）",
  category="学科竞赛", competition_level="校级",
  eligible_participants="全校本科生", team_size="3 人",
  registration_start=None, registration_deadline=None, event_start=None, event_end=None,
  description="【演示数据】没有报名日期和截止日期的记录，用于验证待确认与动态状态兜底。",
  requirements=None, registration_url=None, verification_status="incomplete", confidence=0.32,
  verification_notes="演示记录：报名日期和作品要求缺失，不得根据经验推测。",
  missing_fields=["registration_start", "registration_deadline", "event_start", "event_end", "requirements", "registration_url"]),
]
RECORDS += [
r(id="demo-006", title="【模拟】校园文化创意产品设计赛",
  organizer="演示主办方 · 校园文化中心（非真实机构）",
  category="文化创意", competition_level="校级",
  eligible_participants="全校学生", team_size="1–5 人",
  registration_start=iso(dt(15)), registration_deadline=iso(datetime(2026,11,8,23,59,59,tzinfo=TZ)),
  description="【演示数据】没有报名入口链接的记录，用于展示信息不完整和待核验提示。",
  requirements="模拟要求：提交文创产品设计图、材质说明和成本测算。",
  registration_url=None, verification_status="incomplete", confidence=0.48,
  verification_notes="演示记录：官方报名入口未确认，禁止猜测链接。", missing_fields=["registration_url"]),
r(id="demo-007", title="【模拟】青年社会实践项目大赛",
  organizer="演示主办方 · 校团委实践部（非真实机构）",
  category="社会实践", competition_level="省级",
  eligible_participants="高校在校生，团队负责人须为本科生", team_size="4–8 人",
  registration_start=iso(dt(1, 9, 9)), registration_deadline=iso(datetime(2026,10,27,17,0,0,tzinfo=TZ)),
  description="【演示数据】官方通知链接被标记为异常的记录，用于验证链接异常状态与人工复核提示。",
  requirements="模拟要求：提交项目申报书、实践照片和单位接收证明。",
  official_notice_url="https://example.com/demo-broken-notice-404", registration_url=None,
  verification_status="broken", confidence=0.42,
  verification_notes="演示记录：模拟链接异常（HTTP 404）；页面无法核验，不能标记为官方确认。",
  missing_fields=["registration_url"],
  verification_history=[{"checked_at": iso(dt(24, 20)), "status": "broken", "method": "http_head", "note": "模拟：HTTP 404 Not Found。", "http_status": 404}]),
]
RECORDS += [
r(id="demo-008", title="【模拟】大学生思政微课堂展示活动",
  organizer="演示主办方 · 学生工作部（非真实机构）",
  category="思政教育", competition_level="校级",
  eligible_participants="全校本科生、研究生", team_size="1–2 人",
  registration_start=None, registration_deadline=None, event_start=None, event_end=None,
  description="【演示数据】来自待人工核验内容的记录；报名时间未知，不允许编造截止日期。",
  requirements="模拟要求：提交 5 分钟微课堂视频和讲稿。",
  official_notice_url=None, registration_url=None, source_type="wechat_manual",
  source_name="手动提交的公众号链接（演示）", source_url="https://example.com/demo-wechat-article",
  verification_status="pending", confidence=0.28,
  verification_notes="演示记录：公众号内容未经官方原文核实，已进入待核验队列。",
  missing_fields=["official_notice_url", "registration_start", "registration_deadline", "registration_url"]),
r(id="demo-009", title="【模拟】全国大学生智能应用创新赛",
  organizer="演示主办方 · 智能科技教育联盟（非真实机构）",
  category="人工智能", competition_level="国家级",
  eligible_participants="普通高校在校生", team_size=None,
  registration_start=iso(dt(12)), registration_deadline=iso(datetime(2026,12,1,23,59,59,tzinfo=TZ)),
  description="【演示数据】团队人数缺失的 AI 类竞赛记录，用于验证缺失字段展示。",
  requirements="模拟要求：提交算法说明、可复现实验记录和应用展示。",
  registration_url="https://example.com/demo-register-009", verification_status="incomplete",
  confidence=0.66, verification_notes="演示记录：团队人数未在原文确认，前端必须显示待确认。",
  missing_fields=["team_size"]),
]
RECORDS += [
r(id="demo-010", title="【模拟】高校青年公益创意行动赛",
  organizer="演示主办方 · 公益实践中心（非真实机构）",
  category="其他", competition_level="校级",
  eligible_participants="全校学生", team_size="2–6 人",
  registration_start=iso(dt(20, 9, 9)), registration_deadline=iso(datetime(2026,10,20,23,59,59,tzinfo=TZ)),
  event_start=iso(dt(25, 9)), event_end=iso(dt(30, 18)),
  description="【演示数据】报名已结束但活动尚未开始的记录，用于验证不同的时间状态展示。",
  requirements="模拟要求：提交公益行动方案和可执行预算。",
  registration_url=None, verification_status="verified", confidence=0.7,
  verification_notes="演示记录：模拟核验状态；未访问真实赛事页面。",
  missing_fields=["registration_url"]),
]

def registration_status(record: dict) -> str:
    deadline = record.get("registration_deadline")
    start = record.get("registration_start")
    if deadline and NOW > datetime.fromisoformat(deadline):
        return "closed"
    if start and NOW < datetime.fromisoformat(start):
        return "upcoming"
    return "open" if (start or deadline) else "unknown"

records = []
for raw in RECORDS:
    rec = json.loads(json.dumps(raw, ensure_ascii=False))
    if rec.get("source_url") == BASE["source_url"]:
        rec["source_url"] = f"https://example.com/demo-fixture/{rec['id']}"
    if rec.get("official_notice_url") == BASE["official_notice_url"]:
        rec["official_notice_url"] = f"https://example.com/demo-notice/{rec['id']}"
    rec["registration_status"] = registration_status(rec)
    canonical = json.dumps({k: rec.get(k) for k in ["id", "title", "organizer", "registration_deadline", "official_notice_url"]}, ensure_ascii=False, sort_keys=True)
    rec["content_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    records.append(rec)
OUT.mkdir(parents=True, exist_ok=True)
competitions = {
    "schema_version": "1.0.0", "data_mode": "demo", "generated_at": iso(NOW),
    "notice": "全部记录均为合成演示数据，不是真实赛事。请勿依据本数据报名或对外发布。",
    "record_count": len(records), "records": records,
}
(OUT / "competitions.json").write_text(json.dumps(competitions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

sources = {
    "schema_version": "1.0.0", "data_mode": "demo", "generated_at": iso(NOW),
    "notice": "以下信息源均为合成名称，未抓取或验证任何真实网站。",
    "sources": [
        {"id": "src-demo-innovation", "name": "演示信息源 A · 高校创新通知（合成）", "source_type": "html_list", "domain": "example.com", "list_url": "https://example.com/demo-innovation-list", "enabled": True, "update_frequency": "daily", "last_checked_at": iso(dt(24, 20)), "last_success_at": iso(dt(24, 20)), "status": "demo", "result": "演示：模拟发现 4 条通知", "failure_reason": None, "records_found": 4, "records_added": 4, "needs_manual_verification": False, "manual_verification_count": 0, "verified": False, "is_demo": True},
        {"id": "src-demo-ai", "name": "演示信息源 B · AI 赛事公告（合成）", "source_type": "rss", "domain": "example.com", "list_url": "https://example.com/demo-ai-feed", "enabled": True, "update_frequency": "daily", "last_checked_at": iso(dt(24, 20)), "last_success_at": iso(dt(23, 18)), "status": "demo", "result": "演示：模拟发现 3 条公告，其中 2 条待核验", "failure_reason": None, "records_found": 3, "records_added": 2, "needs_manual_verification": True, "manual_verification_count": 2, "verified": False, "is_demo": True},
        {"id": "src-demo-manual", "name": "演示信息源 C · 手动公众号待核验（合成）", "source_type": "wechat_manual", "domain": "example.com", "list_url": None, "enabled": True, "update_frequency": "manual", "last_checked_at": iso(dt(24, 19)), "last_success_at": None, "status": "demo", "result": "演示：模拟进入人工核验队列", "failure_reason": "无真实文章，未进行网络请求", "records_found": 1, "records_added": 0, "needs_manual_verification": True, "manual_verification_count": 3, "verified": False, "is_demo": True},
    ],
}
(OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

run_history = [
    {"run_id": "demo-run-20261024", "started_at": iso(NOW), "finished_at": iso(dt(24, 20)), "status": "demo", "message": "演示数据加载，非真实采集任务", "records_added": 0, "records_updated": 0},
    {"run_id": "demo-run-20261023", "started_at": iso(dt(23, 18)), "finished_at": iso(dt(23, 18)), "status": "demo", "message": "模拟历史运行", "records_added": 0, "records_updated": 0},
]
meta = {
    "schema_version": "1.0.0", "data_mode": "demo", "generated_at": iso(NOW),
    "last_run": {"started_at": iso(dt(24, 20)), "finished_at": iso(NOW), "status": "demo", "message": "当前展示的是内置演示数据，不代表任何真实采集已成功运行。"},
    "summary": {"source_count": len(sources["sources"]), "success_count": 0, "failure_count": 0, "record_count": len(records), "pending_verification_count": sum(1 for x in records if x["verification_status"] in ("pending", "broken", "incomplete"))},
    "run_history": run_history,
    "notice": "本文件中的运行记录为演示；GitHub Actions 自动更新尚未在该工作区运行。",
}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
missing_counts = {}
verification_breakdown = {}
for rec in records:
    for key in rec["missing_fields"]:
        missing_counts[key] = missing_counts.get(key, 0) + 1
    verification_breakdown[rec["verification_status"]] = verification_breakdown.get(rec["verification_status"], 0) + 1
quality = {
    "schema_version": "1.0.0", "data_mode": "demo", "generated_at": iso(NOW),
    "record_count": len(records), "duplicate_id_count": 0, "duplicate_url_count": 0, "duplicate_title_count": 0,
    "missing_field_counts": missing_counts, "verification_breakdown": verification_breakdown,
    "records_needing_manual_review": [x["id"] for x in records if x["verification_status"] in ("pending", "broken", "incomplete")],
    "notes": ["全部为合成演示数据，不是真实赛事，请勿用于报名。", "演示数据覆盖：正在报名、即将截止、已截止、无截止日期、无报名链接、链接异常、待人工核验。", "重复公告场景位于 tests/fixtures/competitions.edge-cases.json，通过去重测试验证，不进入展示数据。"],
}
(OUT / "quality-report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(OUT / "run-history.json").write_text(json.dumps({"schema_version": "1.0.0", "data_mode": "demo", "runs": run_history, "notice": "演示运行历史，不是真实 Actions 运行记录。"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

duplicate = json.loads(json.dumps(records[0], ensure_ascii=False))
duplicate["id"] = "demo-001-duplicate-announcement"
duplicate["source_url"] = records[0]["source_url"] + "?utm_source=duplicate"
duplicate["source_name"] = "重复公告演示来源（合成）"
fixture = {"schema_version": "1.0.0", "data_mode": "demo", "notice": "测试夹具：全部为合成模拟数据，不是真实赛事。覆盖正在报名、即将截止、已截止、无截止、无报名链接、链接异常、重复公告、待人工核验等场景。", "records": records + [duplicate]}
(FIX / "competitions.edge-cases.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(records)} demo records, {len(sources['sources'])} demo sources")
print("Verification:", verification_breakdown)
print("Missing fields:", missing_counts)

# --- Published demo reports aligned with the CI contract ---
sources["source_count"] = len(sources["sources"])
sources["enabled_count"] = sum(1 for s in sources["sources"] if s.get("enabled") is True)
(OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

VERIFICATION_KEYS = ["verified", "pending", "broken", "expired", "incomplete"]
REGISTRATION_KEYS = ["open", "upcoming", "closed", "unknown"]
COVERAGE_FIELDS = ["organizer", "category", "competition_level", "eligible_participants", "team_size", "registration_start", "registration_deadline", "event_start", "event_end", "description", "requirements", "official_notice_url", "registration_url", "published_at", "region"]
verification_counts = {key: sum(1 for rec in records if rec["verification_status"] == key) for key in VERIFICATION_KEYS}
registration_counts = {key: sum(1 for rec in records if rec["registration_status"] == key) for key in REGISTRATION_KEYS}
field_coverage = {}
for field in COVERAGE_FIELDS:
    present = sum(1 for rec in records if rec.get(field) is not None)
    field_coverage[field] = {"present": present, "total": len(records), "percent": round(present / len(records) * 100, 1) if records else 0.0}
pending_verification = sum(1 for rec in records if rec["verification_status"] in ("pending", "broken", "incomplete"))
summary_text = f"演示模式：共 {len(records)} 条合成记录，待核验或信息不全 {pending_verification} 条；3 个合成来源均未进行真实网络采集。"
quality = {
    "schema_version": "1.0.0",
    "data_mode": "demo",
    "generated_at": iso(NOW),
    "summary": {
        "message": summary_text,
        "record_count": len(records),
        "pending_verification_count": pending_verification,
        "verified_record_count": verification_counts["verified"],
    },
    "summary_text": summary_text,
    "totals": {
        "record_count": len(records),
        "verified_record_count": verification_counts["verified"],
        "pending_verification_count": pending_verification,
        "source_count": len(sources["sources"]),
        "enabled_source_count": sources["enabled_count"],
        "successful_source_count": 0,
        "failed_source_count": 0,
        "disabled_source_count": 0,
        "links_checked": 0,
    },
    "verification_status_counts": verification_counts,
    "registration_status_counts": registration_counts,
    "field_coverage": field_coverage,
    "missing_field_counts": missing_counts,
    "link_check_summary": {
        "ok": 0, "redirect": 0, "timeout": 0, "forbidden": 0, "not_found": 0,
        "connection_error": 0, "js_required_page": 0, "server_error": 0,
        "http_error": 0, "invalid_url": 0, "unknown": 0, "not_checked": len(records),
    },
    "source_summary": {
        "total": len(sources["sources"]), "enabled": sources["enabled_count"],
        "success": 0, "failed": 0, "disabled": 0,
        "verified": 0, "needs_manual_verification": sum(1 for item in sources["sources"] if item.get("needs_manual_verification") is True),
    },
    "warnings": [
        "当前全部为合成演示数据，不是真实赛事，禁止作为报名依据。",
        "没有真实信息源经过人工核验；演示来源不得标记为官方确认。",
        "演示链接仅用于展示字段与异常状态，不进行真实网络采集。",
        "真实上线前请启用并人工核验 collector/sources.json 中的公开官方来源。",
    ],
    "notice": "质量报告描述演示字段完整度，不构成对赛事真实性、报名开放状态或主办方授权的认证。",
    "record_count": len(records),
    "duplicate_id_count": 0,
    "duplicate_url_count": 0,
    "duplicate_title_count": 0,
    "records_needing_manual_review": [x["id"] for x in records if x["verification_status"] in ("pending", "broken", "incomplete")],
    "notes": [
        "演示数据覆盖：正在报名、即将截止、已截止、无截止日期、无报名链接、链接异常、待人工核验。",
        "重复公告场景位于 tests/fixtures/competitions.edge-cases.json，通过去重测试验证，不进入展示数据。",
    ],
}
(OUT / "quality-report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

demo_logs = [
    {"run_id": "demo-run-20261024", "timestamp": iso(NOW), "level": "info", "event": "demo_loaded", "message": "加载内置演示数据；未进行真实网络采集。", "details": {"record_count": len(records), "data_mode": "demo"}},
    {"run_id": "demo-run-20261024", "timestamp": iso(dt(24, 20)), "level": "warning", "event": "demo_not_verified", "message": "演示来源与链接均未核验，禁止标记为官方确认。", "details": {}},
    {"run_id": "demo-run-20261024", "timestamp": iso(dt(24, 20)), "level": "info", "event": "demo_finished", "message": "演示数据质量报告生成完成。", "details": {"records": len(records)}},
]
with (OUT / "run-log.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
    for entry in demo_logs:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
