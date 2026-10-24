"""从候选条目中保守抽取赛事字段；无法确认一律返回 None。"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit

from .dates import (
    TZ,
    normalize_text,
    parse_datetime,
    parse_event_period,
    parse_registration_deadline,
    parse_registration_period,
)
from .dedupe import canonicalize_url
from .schema import blank_competition_record, normalize_competition_record, now_iso

ORGANIZER_RE = re.compile(
    r"(?:主办单位|主办方|主办机构|主办)\s*[：:]\s*([^\n。；;]{2,90})"
)
ORGANIZER_BY_RE = re.compile(
    r"由\s*([^\n。；;]{2,70}?)\s*(?:主办|承办)"
)
ELIGIBLE_RE = re.compile(
    r"(?:参赛对象|参赛资格|报名对象|参赛人员|参与对象|面向对象)\s*[：:]?\s*([^\n。；;]{2,120})"
)
ELIGIBLE_FACING_RE = re.compile(
    r"面向\s*((?:全国|全省|全校|普通高校|高校|全日制)[^\n。；;]{2,100})"
)
ELIGIBLE_TERMS = (
    "学生", "本科生", "研究生", "专科生", "高职", "高校", "院校",
    "在校", "学籍", "全日制", "参赛队", "团队", "个人",
)
REQUIREMENTS_RE = re.compile(
    r"(?:作品要求|提交要求|参赛作品要求|材料要求|作品规格|提交材料|参赛要求)\s*[：:]?\s*([^\n]{2,400})"
)
REGISTRATION_URL_RE = re.compile(
    r"(?:报名链接|报名网址|报名入口|在线报名|报名系统|报名平台)\s*[：:\s]*"
    r"(https?://[^\s<>\"'）)\]，,；;]+)",
    re.I,
)
GENERIC_URL_RE = re.compile(r"https?://[^\s<>\"'）)\]，,；;]+", re.I)

CATEGORY_RULES = (
    ("数学建模", ("数学建模", "数模")),
    ("程序设计", ("程序设计", "编程", "算法", "软件开发", "人工智能", "大数据", "网络安全", "计算机设计")),
    ("电子设计", ("电子设计", "嵌入式", "单片机", "集成电路", "芯片设计")),
    ("机械工程", ("机械设计", "机器人", "工程训练", "智能制造")),
    ("创新创业", ("创新创业", "互联网+", "挑战杯", "创青春", "创业计划")),
    ("艺术设计", ("艺术设计", "广告艺术", "视觉传达", "数字媒体", "摄影", "文创")),
    ("外语", ("英语", "外语", "翻译", "口译")),
    ("学术科技", ("学术科技", "科研", "论文", "科技创新")),
    ("商业案例", ("商业案例", "市场营销", "商赛", "经济分析")),
    ("公益实践", ("公益", "志愿服务", "社会实践", "乡村振兴")),
    ("体育", ("体育", "运动", "健身")),
    ("征文", ("征文", "文学创作", "写作")),
)

PROVINCES = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港",
    "澳门", "台湾",
)
_EXPLICIT_LEVEL_RE = re.compile(r"(国际级|国家级|省级|市级|校级|院级|国际赛|全国赛|省赛|市赛|校赛|院赛)")
_LEVEL_LABEL_RE = re.compile(r"(?:赛事|竞赛|比赛|大赛)?级别\s*[：:]\s*([^。；;，,\s]{1,20})")


def _map_explicit_level(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    if re.search(r"国际级|国际赛", text):
        return "国际级"
    if re.search(r"国家级|全国赛", text):
        return "国家级"
    if re.search(r"省级|省赛", text):
        return "省级"
    if re.search(r"市级|市赛", text):
        return "市级"
    if re.search(r"校级|校赛", text):
        return "校级"
    if re.search(r"院级|院赛", text):
        return "院级"
    return None
def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = normalize_text(value)
    if not text:
        return None
    return text[:limit].rstrip("，,；;。 ")


def _strip_label_tail(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_text(value)
    text = re.split(
        r"(?:承办单位|协办单位|支持单位|指导单位|联系方式|报名时间|报名截止|比赛时间|奖项设置|参赛费用|作品要求)\s*[：:]",
        text,
        maxsplit=1,
    )[0]
    return _truncate(text, 120)


def _clean_title(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    text = re.sub(r"^(?:20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?)\s*", "", text)
    return text.strip(" -—|·") or None


def extract_organizer(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text((item or {}).get("organizer"))
    if explicit:
        return _strip_label_tail(explicit)
    for pattern in (ORGANIZER_RE, ORGANIZER_BY_RE):
        match = pattern.search(text)
        if match:
            return _strip_label_tail(match.group(1))
    return None


def extract_category(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text((item or {}).get("category"))
    if explicit:
        return _truncate(explicit, 40)
    haystack = normalize_text(text)
    for category, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


def extract_level(text: str, item: dict[str, Any] | None = None) -> str | None:
    item = item or {}
    for value in (item.get("competition_level"), item.get("level"), item.get("title")):
        level = _map_explicit_level(value)
        if level:
            return level
    label_match = _LEVEL_LABEL_RE.search(text)
    if label_match:
        label_value = normalize_text(label_match.group(1))
        level = _map_explicit_level(label_value)
        if level:
            return level
        if label_value.startswith(("全国", "国家")):
            return "国家级"
        if label_value.startswith("国际"):
            return "国际级"
    match = _EXPLICIT_LEVEL_RE.search(normalize_text(text)[:300])
    return _map_explicit_level(match.group(1)) if match else None

def extract_region(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text(
        (item or {}).get("region") or (item or {}).get("province")
    )
    if explicit:
        return _truncate(explicit, 40)
    title = normalize_text((item or {}).get("title"))
    if re.search(r"国际|全球|世界", title):
        return "国际"
    if "全国" in title:
        return "全国"
    for province in PROVINCES:
        if province in title:
            return province
    match = re.search(r"(?:举办地|赛区|地区|地点)\s*[：:]\s*([^\s，,。；;]{2,30})", text)
    if match:
        return _truncate(match.group(1), 30)
    return None
def extract_eligible_participants(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text((item or {}).get("eligible_participants"))
    if explicit:
        return _truncate(explicit, 120)
    for match in ELIGIBLE_RE.finditer(text):
        value = re.split(r"(?:参赛要求|组队要求|作品要求|报名时间|报名截止)", match.group(1))[0]
        if any(term in value for term in ELIGIBLE_TERMS):
            return _truncate(value, 120)
    for match in ELIGIBLE_FACING_RE.finditer(text):
        value = re.split(
            r"(?:的(?:赛事|活动|竞赛|比赛|平台|项目)|组织开展|开展|参加|参赛)",
            match.group(1),
            maxsplit=1,
        )[0]
        if any(term in value for term in ELIGIBLE_TERMS) and not re.search(
            r"负责人|培训|承办|教师|组织者", value
        ):
            return _truncate(value, 120)
    for phrase in (
        "全日制在校本科生", "全日制本科生", "全日制在校本科",
        "全日制在校大学生", "在校本科生", "在校研究生", "高校在校生",
        "高校学生", "高职高专学生", "高职院校学生", "普通高校在校生",
    ):
        if phrase in text:
            return phrase
    return None


def extract_team_size(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text((item or {}).get("team_size"))
    if explicit:
        return _truncate(explicit, 60)
    normalized = normalize_text(text)
    # 教师人数不是学生团队规模。按标点切开并剔除提到教师的片段，避免误抓。
    student_context = "。".join(
        part for part in re.split(r"[，,；;。]", normalized)
        if part.strip() and not re.search(r"指导教师|指导老师|教师", part)
    )
    patterns = (
        (re.compile(r"(?:每队|每个团队|每支队伍|每组|团队|小组|队伍)\s*(?:人数)?\s*(?:为|由|限)?\s*(\d+)\s*[-~至到—–]\s*(\d+)\s*人"), "range"),
        (re.compile(r"(?:每个参赛队|每支参赛队|每队|每个团队|每支队伍).{0,18}?(?:由|为|限|包含)?\s*(\d+)\s*[-~至到—–]\s*(\d+)\s*(?:名|人)"), "range"),
        (re.compile(r"(?:每队|每个团队|每支队伍|团队|小组|队伍).{0,10}?(?:不超过|最多|至多|限)\s*(\d+)\s*人"), "max"),
        (re.compile(r"(?:每队|每个团队|每支队伍|团队|小组|队伍)\s*(\d+)\s*人"), "exact"),
        (re.compile(r"(?:每个参赛队|每支参赛队|每队|每个团队|每支队伍).{0,18}?(?:由|为|限|包含)?\s*(\d+)\s*(?:名|人)"), "exact"),
        (re.compile(r"(\d+)\s*人\s*(?:一队|每组|每队)"), "exact"),
        (re.compile(r"(?:至少\s*(\d+)\s*人).{0,12}?(?:最多|不超过)\s*(\d+)\s*人"), "range"),
    )
    for pattern, kind in patterns:
        match = pattern.search(student_context)
        if not match:
            continue
        if kind == "range":
            low, high = int(match.group(1)), int(match.group(2))
            if low <= high:
                return f"{low}-{high}人"
        elif kind == "max":
            return f"不超过{int(match.group(1))}人"
        else:
            return f"{int(match.group(1))}人"
    if re.search(r"(?:个人赛|单人赛)", normalized):
        return "个人赛"
    if re.search(r"(?:团队赛|团体赛)", normalized):
        return "团队赛"
    return None


def extract_requirements(text: str, item: dict[str, Any] | None = None) -> str | None:
    explicit = normalize_text((item or {}).get("requirements") or (item or {}).get("work_requirements"))
    if explicit:
        return _truncate(explicit, 400)
    match = REQUIREMENTS_RE.search(text)
    if not match:
        return None
    value = re.split(r"(?:报名|截止|参赛对象|参赛资格|主办单位|联系方式|奖项|费用)\s*[：:]", match.group(1))[0]
    return _truncate(value, 400)


def extract_explicit_registration_url(text: str, item: dict[str, Any] | None = None) -> str | None:
    """只接受明确标注为报名入口的 URL，绝不把通知页或首页当报名页。"""
    explicit = normalize_text((item or {}).get("registration_url"))
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    candidates.extend(match.group(1) for match in REGISTRATION_URL_RE.finditer(text))
    for candidate in candidates:
        parts = urlsplit(candidate)
        if parts.scheme in ("http", "https") and parts.netloc:
            return candidate.rstrip("。，,；;）)]}")
    return None
def extract_item(item: dict[str, Any], source: dict[str, Any], *,
                 now: str | None = None) -> dict[str, Any] | None:
    """把一个候选条目转换为符合字段契约的记录；信息不足字段保持 null。"""
    title = _clean_title(item.get("title"))
    if not title:
        return None
    stamp = now or now_iso()
    content = normalize_text(item.get("content") or item.get("summary") or title)
    summary = normalize_text(item.get("summary"))
    extraction_text = normalize_text(f"{title} {content}")

    official_url = normalize_text(item.get("url") or item.get("official_notice_url"))
    can_url = canonicalize_url(official_url)
    registration_start = parse_datetime(item.get("registration_start"))
    registration_deadline = parse_datetime(item.get("registration_deadline"), end_of_day=True)
    event_start = parse_datetime(item.get("event_start"))
    event_end = parse_datetime(item.get("event_end"), end_of_day=True)

    period_start, period_end = parse_registration_period(extraction_text)
    registration_start = registration_start or period_start
    registration_deadline = registration_deadline or period_end
    explicit_deadline = parse_registration_deadline(extraction_text)
    if explicit_deadline:
        registration_deadline = explicit_deadline
    event_start = event_start or parse_event_period(extraction_text)[0]
    event_end = event_end or parse_event_period(extraction_text)[1]

    description = _truncate(content, 6000)
    if description and normalize_text(description) == title and not summary:
        description = None
    if summary and len(summary) > len(content):
        description = _truncate(summary, 6000)

    record = blank_competition_record()
    record.update({
        "title": title,
        "organizer": extract_organizer(extraction_text, item),
        "category": extract_category(extraction_text, item),
        "competition_level": extract_level(extraction_text, item),
        "eligible_participants": extract_eligible_participants(extraction_text, item),
        "team_size": extract_team_size(extraction_text, item),
        "registration_start": registration_start,
        "registration_deadline": registration_deadline,
        "event_start": event_start,
        "event_end": event_end,
        "description": description,
        "requirements": extract_requirements(extraction_text, item),
        "official_notice_url": official_url,
        "registration_url": extract_explicit_registration_url(extraction_text, item),
        "source_name": source.get("name"),
        "source_url": official_url,
        "source_list_url": source.get("list_url"),
        "source_id": source.get("id"),
        "source_type": source.get("source_type"),
        "canonical_url": can_url,
        "published_at": parse_datetime(item.get("published_at")),
        "fetched_at": stamp,
        "last_verified_at": None,
        "verification_status": "pending",
        "verification_notes": "自动采集，尚未人工核验；来源尚未验证，链接可访问不代表报名开放。",
        "confidence": 0.0,
        "region": extract_region(extraction_text, item),
        "is_demo": False,
        "verification_history": [],
        "change_history": [],
        "link_check": item.get("link_check"),
        "registration_link_check": item.get("registration_link_check"),
        "detail_fetch": item.get("detail_fetch"),
    })
    detail = record.get("detail_fetch")
    if isinstance(detail, dict) and detail.get("error"):
        record["verification_notes"] = (
            "列表页已采集，但详情正文未能获取，关键字段可能缺失，需人工核验。"
        )
    return normalize_competition_record(record, now=stamp, source=source)


def extract_items(items: list[dict[str, Any]], source: dict[str, Any], *,
                  now: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        try:
            record = extract_item(item, source, now=now)
            if record is not None:
                records.append(record)
        except Exception as exc:  # 单条坏数据不拖垮一个来源。
            errors.append(f"第 {index + 1} 条抽取失败: {type(exc).__name__}: {exc}")
    return records, errors