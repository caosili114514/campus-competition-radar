"""公开 HTML 列表、RSS/Atom 与 JSON feed 解析器。

每个解析器只负责把原始内容变成统一候选条目；字段抽取由 extractors.py 完成。
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit

from .dates import find_dates, normalize_text, parse_datetime


def strip_html(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(unescape(text))


def _valid_link(href: str | None, base_url: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    absolute = urljoin(base_url or "", href)
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https", "fixture") or not parts.netloc:
        return None
    if re.search(r"\.(?:css|js|png|jpe?g|gif|svg|ico|woff2?)(?:$|\?)", parts.path, re.I):
        return None
    return absolute
_NAV_TITLES = {
    "首页", "返回", "更多", "查看更多", "详情", "阅读全文", "登录", "注册",
    "联系我们", "关于我们", "网站地图", "上一页", "下一页", "通知公告",
}
_CONTAINER_TAGS = {"li", "article", "tr"}
_CONTAINER_CLASS_RE = re.compile(r"(?:news|item|list|card|article|post|notice|competition|match)", re.I)
_CONTEST_HINT_RE = re.compile(r"(?:竞赛|大赛|比赛|赛事|报名|作品|挑战杯|创新创业|建模|设计|征文)")


class _ListPageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.anchor: dict[str, Any] | None = None
        self.fallback_anchors: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "time" and attrs_map.get("datetime"):
            for container in self.stack:
                container["time_values"].append(attrs_map["datetime"])
        is_container = tag in _CONTAINER_TAGS or (
            tag in ("div", "section", "ul") and _CONTAINER_CLASS_RE.search(attrs_map.get("class", ""))
        )
        if is_container:
            self.stack.append({"tag": tag, "texts": [], "anchors": [], "time_values": []})
        if tag == "a":
            self.anchor = {
                "href": attrs_map.get("href"),
                "attr_title": attrs_map.get("title", ""),
                "texts": [],
                "in_container": bool(self.stack),
            }
            for container in self.stack:
                container["anchors"].append(self.anchor)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self.anchor is not None:
            self.anchor["texts"].append(data)
        for container in self.stack:
            container["texts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self.anchor is not None:
            anchor = self.anchor
            title = normalize_text("".join(anchor["texts"]) or anchor.get("attr_title"))
            anchor["title"] = title
            clean_url = _valid_link(anchor.get("href"), self.base_url)
            anchor["url"] = clean_url
            if not anchor.get("in_container"):
                self.fallback_anchors.append(anchor)
            self.anchor = None
        if any(container["tag"] == tag for container in self.stack):
            while self.stack:
                container = self.stack.pop()
                if container["tag"] == tag:
                    self._finalize_container(container)
                    break

    def _finalize_container(self, container: dict[str, Any]) -> None:
        content = normalize_text(" ".join(container["texts"]))
        published = None
        for raw in container.get("time_values", []):
            published = parse_datetime(raw)
            if published:
                break
        if not published:
            dates = find_dates(content)
            if dates:
                published = dates[0]
        seen_urls: set[str] = set()
        for anchor in container["anchors"]:
            title = normalize_text(anchor.get("title"))
            url = anchor.get("url")
            if not url or url in seen_urls or not self._meaningful(title, content):
                continue
            seen_urls.add(url)
            self.candidates.append({
                "title": title,
                "url": url,
                "published_at": published,
                "summary": content[:500] or None,
                "content": content or title,
                "source_item_id": None,
            })

    @staticmethod
    def _meaningful(title: str, content: str) -> bool:
        if not title or title in _NAV_TITLES:
            return False
        if len(title) < 2:
            return False
        if _CONTEST_HINT_RE.search(title) or _CONTEST_HINT_RE.search(content):
            return True
        return len(title) >= 4
    def all_items(self) -> list[dict[str, Any]]:
        self.close()
        raw_items = list(self.candidates)
        for anchor in self.fallback_anchors:
            title = normalize_text(anchor.get("title"))
            url = anchor.get("url")
            if url and self._meaningful(title, title):
                raw_items.append({
                    "title": title, "url": url, "published_at": None,
                    "summary": None, "content": title, "source_item_id": None,
                })
        best: dict[str, dict[str, Any]] = {}
        for item in raw_items:
            key = item["url"]
            existing = best.get(key)
            if existing is None or len(item.get("content") or "") > len(existing.get("content") or ""):
                best[key] = item
        return list(best.values())


class HtmlListParser:
    name = "html"

    def parse(self, text: str, source: dict[str, Any], *, base_url: str | None = None) -> list[dict[str, Any]]:
        parser = _ListPageParser(base_url or source.get("list_url") or "")
        parser.feed(text or "")
        return parser.all_items()
def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _first_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) in names:
            value = normalize_text("".join(child.itertext()))
            if value:
                return value
    return None


class RssAtomParser:
    name = "rss"

    def parse(self, text: str, source: dict[str, Any], *, base_url: str | None = None) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(text or "")
        except ET.ParseError as exc:
            raise ValueError(f"RSS/Atom XML 解析失败: {exc}") from exc
        items: list[dict[str, Any]] = []
        for element in root.iter():
            local = _local_name(element.tag)
            if local not in ("item", "entry"):
                continue
            title = _first_text(element, ("title",)) or ""
            link = None
            for child in element:
                if _local_name(child.tag) == "link":
                    candidate = child.attrib.get("href") or normalize_text("".join(child.itertext()))
                    link = _valid_link(candidate, base_url or source.get("list_url"))
                    if link:
                        break
            if not link:
                link = _valid_link(_first_text(element, ("guid", "id")), base_url or source.get("list_url"))
            content = _first_text(element, ("encoded", "content", "description", "summary")) or title
            summary = _first_text(element, ("summary", "description")) or strip_html(content)[:500]
            published = parse_datetime(_first_text(element, ("pubdate", "published", "updated", "date")))
            author = _first_text(element, ("author", "creator"))
            if title.strip():
                items.append({
                    "title": normalize_text(title),
                    "url": link,
                    "published_at": published,
                    "summary": normalize_text(summary)[:500] or None,
                    "content": strip_html(content) or normalize_text(title),
                    "author": author,
                    "source_item_id": _first_text(element, ("guid", "id")),
                })
        return items
def _json_path_get(data: Any, path: str | None) -> Any:
    if not path:
        return data
    value = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _find_json_items(data: Any, source: dict[str, Any]) -> list[Any]:
    selected = _json_path_get(data, source.get("items_path"))
    if isinstance(selected, list):
        return selected
    if isinstance(selected, dict):
        for key in ("items", "records", "data", "competitions", "list"):
            if isinstance(selected.get(key), list):
                return selected[key]
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "records", "competitions", "data", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for nested in ("items", "records", "data"):
                    if isinstance(value.get(nested), list):
                        return value[nested]
    return []


def _json_text(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        text = normalize_text(value)
        if text:
            return text
    return None


class JsonFeedParser:
    name = "json"

    def parse(self, text: str, source: dict[str, Any], *, base_url: str | None = None) -> list[dict[str, Any]]:
        try:
            data = json.loads(text or "")
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON feed 解析失败: {exc}") from exc
        results: list[dict[str, Any]] = []
        for raw in _find_json_items(data, source):
            if not isinstance(raw, dict):
                continue
            title = _json_text(raw, ("title", "name", "competition_name", "notice_title")) or ""
            if not title:
                continue
            raw_url = _json_text(raw, ("url", "link", "official_notice_url", "detail_url", "original_url"))
            url = _valid_link(raw_url, base_url or source.get("list_url"))
            raw_content = None
            for key in ("content_html", "content", "description", "summary", "body", "text"):
                if raw.get(key):
                    raw_content = raw[key]
                    break
            if isinstance(raw_content, (dict, list)):
                raw_content = json.dumps(raw_content, ensure_ascii=False)
            content = strip_html(raw_content) or title
            summary = strip_html(raw.get("summary") or raw.get("description"))[:500] or content[:500]
            results.append({
                "title": title,
                "url": url,
                "published_at": parse_datetime(_json_text(raw, ("published_at", "published", "pubDate", "date", "update_time"))),
                "summary": summary or None,
                "content": content,
                "author": _json_text(raw, ("author", "organizer", "host")),
                "organizer": _json_text(raw, ("organizer", "host", "主办方", "主办单位")),
                "category": _json_text(raw, ("category", "type")),
                "source_item_id": _json_text(raw, ("id", "guid", "uuid")),
            })
        return results
_PARSERS = {
    "html": HtmlListParser(),
    "rss": RssAtomParser(),
    "atom": RssAtomParser(),
    "json": JsonFeedParser(),
}


def get_parser(name: str):
    try:
        return _PARSERS[name]
    except KeyError as exc:
        raise ValueError(f"不支持的 parser: {name}") from exc


def detect_parser(text: str) -> str:
    stripped = (text or "").lstrip("\ufeff \t\r\n")
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if stripped.startswith("<?xml") or "<rss" in stripped[:300].lower() or "<feed" in stripped[:300].lower():
        return "rss"
    return "html"


def parse_items(text: str, source: dict[str, Any], *, base_url: str | None = None) -> list[dict[str, Any]]:
    parser_name = source.get("parser") or "auto"
    if parser_name == "auto":
        parser_name = detect_parser(text)
    return get_parser(parser_name).parse(text, source, base_url=base_url)
_IGNORED_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "iframe"}
_CANDIDATE_ATTR_RE = re.compile(r"(?:^|[-_])(?:content|article|detail|main|news|post|text|body|entry|js_content|rich_media)(?:$|[-_])", re.I)


class _MainContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.ignore_depth = 0
        self.in_title = 0
        self.in_h1 = 0
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.fallback_parts: list[str] = []
        self.time_values: list[str] = []
        self.candidates: list[dict[str, Any]] = []
        self.stack: list[dict[str, Any]] = []
        self.tag_seq = 0
        self.tag_stack: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta":
            key = (attrs_map.get("property") or attrs_map.get("name") or "").lower()
            value = attrs_map.get("content") or attrs_map.get("value")
            if key and value:
                self.meta[key] = value
            return
        self.tag_seq += 1
        current_seq = self.tag_seq
        self.tag_stack.append((tag, current_seq))
        if tag in _IGNORED_TAGS:
            self.ignore_depth += 1
        if tag == "title":
            self.in_title += 1
        if tag == "h1":
            self.in_h1 += 1
        if tag == "time" and attrs_map.get("datetime"):
            self.time_values.append(attrs_map["datetime"])
        if self.ignore_depth:
            return
        attr_text = " ".join((attrs_map.get("id", ""), attrs_map.get("class", ""), attrs_map.get("role", ""))).strip()
        weight = 0
        if tag in ("article", "main"):
            weight = 300
        elif tag in ("div", "section") and _CANDIDATE_ATTR_RE.search(attr_text):
            weight = 200
        if weight:
            self.stack.append({"tag": tag, "weight": weight, "parts": [], "start_seq": current_seq})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "meta":
            self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.in_h1:
            self.h1_parts.append(data)
        if self.stack:
            for candidate in self.stack:
                candidate["parts"].append(data)
        self.fallback_parts.append(data)
    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS and self.ignore_depth > 0:
            self.ignore_depth -= 1
        if tag == "title" and self.in_title > 0:
            self.in_title -= 1
        if tag == "h1" and self.in_h1 > 0:
            self.in_h1 -= 1
        match_index = None
        for index in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[index][0] == tag:
                match_index = index
                break
        if match_index is None:
            return
        closed_seq = self.tag_stack[match_index][1]
        del self.tag_stack[match_index:]
        for candidate in list(self.stack):
            if candidate.get("start_seq") == closed_seq:
                text = normalize_text(" ".join(candidate["parts"]))
                self.candidates.append({
                    "text": text,
                    "weight": int(candidate.get("weight", 0)),
                    "score": int(candidate.get("weight", 0)) + min(len(text), 3000) / 10,
                })
                self.stack.remove(candidate)

    def all_content(self) -> dict[str, Any]:
        self.close()
        best = None
        for candidate in self.candidates:
            if len(candidate["text"]) >= 30 and (best is None or candidate["score"] > best["score"]):
                best = candidate
        fallback = normalize_text(" ".join(self.fallback_parts))
        content = best["text"] if best else fallback
        content = re.sub(r"^(?:当前位置|您的位置)\s*[：:].{0,120}?(?=\s|$)", "", content).strip()
        title = (normalize_text(" ".join(self.h1_parts)) or normalize_text(self.meta.get("og:title"))or normalize_text(self.meta.get("pagetitle")) or normalize_text(" ".join(self.title_parts)))
        title = re.sub(r"\s*[-_|—]\s*(?:微信公众平台|微信公众号|官方微信)$", "", title).strip()
        if title and content.startswith(title):
            content = content[len(title):].lstrip(" :：-—")
        published_raw = (
            self.meta.get("article:published_time") or self.meta.get("publishdate") or
            self.meta.get("pubdate") or self.meta.get("date") or self.meta.get("og:release_date")
        )
        published = parse_datetime(published_raw)
        if not published:
            for value in self.time_values:
                published = parse_datetime(value)
                if published:
                    break
        if not published:
            head = content[:800]
            for match in re.finditer(r"(发布时间|发布日期|发布于|时间|日期)\s*[：:]\s*", head):
                before = head[max(0, match.start() - 8):match.start()]
                if any(word in before for word in ("报名", "比赛", "活动", "截止", "会议")):
                    continue
                candidates = find_dates(head[match.end():match.end() + 60])
                if candidates:
                    published = candidates[0]
                    break
        summary = _truncate_for_detail(self.meta.get("og:description") or self.meta.get("description") or content, 500)
        return {
            "title": title or None,
            "content": _truncate_for_detail(content, 12000),
            "summary": summary,
            "published_at": published,
            "content_source": "main" if best else "fallback",
        }


def _truncate_for_detail(value: Any, limit: int) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    return text[:limit].rstrip("，,；;。 ")
def extract_main_content(html_text: str) -> dict[str, Any]:
    """从公开 HTML 页抽取主正文，忽略 script/style/nav/header/footer 等。"""
    parser = _MainContentParser()
    try:
        parser.feed(html_text or "")
        return parser.all_content()
    except Exception:
        return {
            "title": None,
            "content": _truncate_for_detail(strip_html(html_text), 12000),
            "summary": _truncate_for_detail(strip_html(html_text), 500),
            "published_at": None,
            "content_source": "fallback_error",
        }