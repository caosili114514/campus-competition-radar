"""日期解析与报名截止状态。

所有输出时间统一为 Asia/Shanghai (UTC+08:00) 的 ISO 8601 字符串。
无法可靠解析时返回 None，不做跨年份或缺失时区的猜测。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import math
import re
import unicodedata
from typing import Iterable

TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
TZ_NAME = "Asia/Shanghai"

_MONTH = r"(?:1[0-2]|0?[1-9])"
_DAY = r"(?:3[01]|[12]\d|0?[1-9])"
_HOUR = r"(?:2[0-3]|[01]?\d)"
_MINUTE = r"(?:[0-5]?\d)"
_SECOND = r"(?:[0-5]?\d)"
_DATE_SEP = r"(?:年|月|[./-])"
_TIME_SEP = r"(?:[:：时点])"
_MINUTE_SEP = r"(?:[:：分])"

_FULL_DATE_RE = re.compile(
    rf"^\s*(?P<year>20\d{{2}})\s*{_DATE_SEP}\s*(?P<month>{_MONTH})\s*"
    rf"{_DATE_SEP}\s*(?P<day>{_DAY})\s*日?"
    rf"(?:\s*(?P<hour>{_HOUR})\s*{_TIME_SEP}\s*(?P<minute>{_MINUTE})"
    rf"(?:\s*{_MINUTE_SEP}\s*(?P<second>{_SECOND})\s*秒?)?)?\s*$"
)
_DATE_RANGE_RE = re.compile(
    rf"(?P<y1>20\d{{2}})\s*{_DATE_SEP}\s*(?P<m1>{_MONTH})\s*"
    rf"{_DATE_SEP}\s*(?P<d1>{_DAY})\s*日?"
    rf"(?:\s*(?P<h1>{_HOUR})\s*{_TIME_SEP}\s*(?P<min1>{_MINUTE})"
    rf"(?:\s*{_MINUTE_SEP}\s*(?P<s1>{_SECOND})\s*秒?)?)?"
    rf"\s*(?:至|到|—|–|－|~|～|——|-)\s*"
    rf"(?:(?P<y2>20\d{{2}})\s*{_DATE_SEP}\s*)?"
    rf"(?P<m2>{_MONTH})\s*{_DATE_SEP}\s*(?P<d2>{_DAY})\s*日?"
    rf"(?:\s*(?P<h2>{_HOUR})\s*{_TIME_SEP}\s*(?P<min2>{_MINUTE})"
    rf"(?:\s*{_MINUTE_SEP}\s*(?P<s2>{_SECOND})\s*秒?)?)?"
)

_DATE_TOKEN_RE = re.compile(
    rf"(?P<year>20\d{{2}})\s*{_DATE_SEP}\s*(?P<month>{_MONTH})\s*"
    rf"{_DATE_SEP}\s*(?P<day>{_DAY})\s*日?"
    rf"(?:\s*(?P<hour>{_HOUR})\s*{_TIME_SEP}\s*(?P<minute>{_MINUTE})"
    rf"(?:\s*{_MINUTE_SEP}\s*(?P<second>{_SECOND})\s*秒?)?)?"
)

_SECTION_BREAK_RE = re.compile(
    r"(?:报名(?:时间|日期|截止|方式|入口|链接|对象|要求|资格|费用)|"
    r"比赛(?:时间|日期)|竞赛(?:时间|日期)|活动(?:时间|日期)|"
    r"作品(?:要求|提交|规格)|参赛(?:对象|资格|要求)|"
    r"主办单位|承办单位|协办单位|联系方式|奖项设置|赛事级别|参赛费用)\s*[：:]"
)


def normalize_text(value: object) -> str:
    """NFKC 规范化并压缩空白，便于中文日期和字段匹配。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()
def _with_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def as_iso(dt: datetime | date | None) -> str | None:
    """将 datetime/date 转为带 +08:00 的 ISO8601。"""
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time(0, 0, 0), tzinfo=TZ)
    return _with_tz(dt).replace(microsecond=0).isoformat(timespec="seconds")


def _make_datetime(year: int, month: int, day: int, hour: int = 0,
                   minute: int = 0, second: int = 0,
                   end_of_day: bool = False) -> datetime | None:
    try:
        if end_of_day and hour == 0 and minute == 0 and second == 0:
            return datetime(year, month, day, 23, 59, 59, tzinfo=TZ)
        return datetime(year, month, day, hour, minute, second, tzinfo=TZ)
    except ValueError:
        return None


def _parse_builtin(value: object, *, end_of_day: bool) -> datetime | None:
    if isinstance(value, datetime):
        return _with_tz(value).replace(microsecond=0)
    if isinstance(value, date):
        return datetime.combine(value, time(23, 59, 59) if end_of_day else time(0, 0, 0), tzinfo=TZ)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), TZ).replace(microsecond=0)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def parse_datetime(value: object, *, end_of_day: bool = False) -> str | None:
    """解析常见格式为带 +08:00 的 ISO8601。

    支持 ISO8601、RFC 822、Unix 秒/毫秒时间戳、中文年月日及可选时间。
    纯日期默认 00:00:00；end_of_day=True 且无时间时使用 23:59:59。
    """
    dt = _parse_builtin(value, end_of_day=end_of_day)
    if dt is not None:
        return as_iso(dt)
    if value is None:
        return None

    text = normalize_text(value)
    if not text:
        return None

    if re.fullmatch(r"\d{10}|\d{13}", text):
        try:
            stamp = int(text)
            if len(text) == 13:
                stamp /= 1000.0
            return as_iso(datetime.fromtimestamp(stamp, TZ))
        except (OverflowError, OSError, ValueError):
            return None

    if re.search(r"[A-Za-z]{3}", text) and ("," in text or re.search(r"[A-Za-z]{3}\s+\d{1,2}", text)):
        try:
            parsed = parsedate_to_datetime(text)
            if parsed is not None:
                return as_iso(_with_tz(parsed).replace(microsecond=0))
        except (TypeError, ValueError, OverflowError):
            pass

    iso_text = text.replace("Z", "+00:00")
    if "T" in iso_text or re.match(r"^20\d{2}-", iso_text):
        try:
            parsed = datetime.fromisoformat(iso_text)
            if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and "T" not in text and ":" not in text:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return as_iso(_with_tz(parsed).replace(microsecond=0))
        except ValueError:
            pass
    match = _FULL_DATE_RE.fullmatch(text)
    if match:
        values = {key: int(match.group(key)) if match.group(key) else 0 for key in ("year", "month", "day", "hour", "minute", "second")}
        parsed = _make_datetime(values["year"], values["month"], values["day"], values["hour"], values["minute"], values["second"], end_of_day=end_of_day)
        return as_iso(parsed) if parsed else None
    return None


def _range_values(match: re.Match[str]) -> tuple[datetime | None, datetime | None]:
    year1 = int(match.group("y1"))
    month1 = int(match.group("m1"))
    day1 = int(match.group("d1"))
    hour1 = int(match.group("h1") or 0)
    min1 = int(match.group("min1") or 0)
    sec1 = int(match.group("s1") or 0)
    year2 = int(match.group("y2") or year1)
    month2 = int(match.group("m2"))
    day2 = int(match.group("d2"))
    hour2 = int(match.group("h2") or 0)
    min2 = int(match.group("min2") or 0)
    sec2 = int(match.group("s2") or 0)
    start = _make_datetime(year1, month1, day1, hour1, min1, sec1)
    end = _make_datetime(year2, month2, day2, hour2, min2, sec2, end_of_day=True)
    return start, end
def find_periods(text: object) -> list[dict[str, str]]:
    """提取文本中所有起始日期加连接符加结束日期区间。"""
    normalized = normalize_text(text)
    periods: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _DATE_RANGE_RE.finditer(normalized):
        start, end = _range_values(match)
        if not start or not end or end < start:
            continue
        key = (as_iso(start) or "", as_iso(end) or "")
        if key in seen:
            continue
        seen.add(key)
        periods.append({"start": key[0], "end": key[1], "raw": match.group(0), "kind": "range"})
    return periods


def find_dates(text: object, *, end_of_day: bool = False) -> list[str]:
    """提取文本中所有完整日期（必须含四位年份）。"""
    normalized = normalize_text(text)
    results: list[str] = []
    seen: set[str] = set()
    for match in _DATE_TOKEN_RE.finditer(normalized):
        values = {key: int(match.group(key)) if match.group(key) else 0 for key in ("year", "month", "day", "hour", "minute", "second")}
        parsed = _make_datetime(values["year"], values["month"], values["day"], values["hour"], values["minute"], values["second"], end_of_day=end_of_day)
        iso = as_iso(parsed) if parsed else None
        if iso and iso not in seen:
            seen.add(iso)
            results.append(iso)
    return results
def _window_after_label(text: str, end_index: int, *, max_chars: int = 260) -> str:
    tail = text[end_index:end_index + max_chars]
    break_match = _SECTION_BREAK_RE.search(tail, pos=1)
    if break_match:
        tail = tail[:break_match.start()]
    return tail.strip(" \t\r\n，,；;：:")


def extract_labeled_dates(text: object, labels: Iterable[str], *,
                          single_as: str = "start") -> tuple[str | None, str | None]:
    """在明确的字段标签后提取日期区间或单个日期。"""
    normalized = normalize_text(text)
    if not normalized:
        return None, None
    labels_pattern = "|".join(f"(?:{item})" for item in labels)
    match = re.search(labels_pattern, normalized, flags=re.IGNORECASE)
    if not match:
        return None, None
    window = _window_after_label(normalized, match.end())
    if not window:
        return None, None

    periods = find_periods(window)
    if periods:
        return periods[0]["start"], periods[0]["end"]

    dates = find_dates(window, end_of_day=(single_as == "end"))
    if len(dates) >= 2 and single_as == "both":
        return dates[0], dates[-1]
    if dates:
        if single_as == "end":
            return None, dates[0]
        if single_as == "both":
            return dates[0], dates[0]
        return dates[0], None
    return None, None

def parse_registration_period(text: object) -> tuple[str | None, str | None]:
    """识别报名时间/报名起止等标签后的区间。"""
    return extract_labeled_dates(
        text,
        [r"报名(?:时间|日期|起止|阶段|期间)", r"报名开始(?:时间|日期)?", r"报名起"],
        single_as="start",
    )


def parse_registration_deadline(text: object) -> str | None:
    """仅识别明确的报名截止/截止日期，不从其他日期猜测。"""
    _, end = extract_labeled_dates(
        text,
        [r"报名截止(?:时间|日期)?"],
        single_as="end",
    )
    return end


def parse_event_period(text: object) -> tuple[str | None, str | None]:
    return extract_labeled_dates(
        text,
        [r"比赛(?:时间|日期)", r"竞赛(?:时间|日期)", r"活动(?:时间|日期)", r"举办(?:时间|日期)"],
        single_as="start",
    )
def derive_registration_status(start: object, deadline: object, *, now: datetime | None = None) -> str:
    """依据明确的报名起止时间动态推导状态，不依据链接是否可访问。"""
    now_dt = _with_tz(now) if isinstance(now, datetime) else datetime.now(TZ)
    start_iso = parse_datetime(start)
    end_iso = parse_datetime(deadline)
    start_dt = datetime.fromisoformat(start_iso) if start_iso else None
    end_dt = datetime.fromisoformat(end_iso) if end_iso else None
    if end_dt is not None:
        if now_dt > end_dt:
            return "closed"
        if start_dt is not None and now_dt < start_dt:
            return "upcoming"
        return "open"
    if start_dt is not None:
        return "upcoming" if now_dt < start_dt else "open"
    return "unknown"


def days_until_deadline(deadline: object, *, now: datetime | None = None) -> int | None:
    """返回距报名截止的自然日向上取整天数；已截止为 0。"""
    end_iso = parse_datetime(deadline)
    if not end_iso:
        return None
    end_dt = datetime.fromisoformat(end_iso)
    now_dt = _with_tz(now) if isinstance(now, datetime) else datetime.now(TZ)
    seconds = (end_dt - now_dt).total_seconds()
    if seconds <= 0:
        return 0
    return max(0, math.ceil(seconds / 86400))


REGISTRATION_STATUS_LABELS = {
    "open": "报名中",
    "upcoming": "未开始",
    "closed": "已截止",
    "unknown": "待确认",
}