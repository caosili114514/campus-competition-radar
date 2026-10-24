"""链接 HTTP 事实核验。

只记录 HTTP 状态、重定向、超时、403/404、连接错误和疑似 JS 页面；
绝不因 200 推断报名开放或资格有效。
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urlsplit

from .dates import TZ
from .fetcher import FetchResult, HttpFetcher

JS_MARKERS = (
    "enable javascript", "javascript is disabled", "please enable javascript",
    "请开启javascript", "请启用javascript", "需要启用javascript",
    "请使用支持javascript的浏览器", "requires javascript",
)
ROOT_MARKERS = ("__next_data__", "__nuxt__", "id=\"app\"", "id='app'", "id=\"root\"", "id='root'")

LINK_STATUS_LABELS = {
    "ok": "HTTP 可达",
    "redirect": "发生重定向",
    "timeout": "请求超时",
    "forbidden": "HTTP 403 禁止访问",
    "not_found": "HTTP 404 未找到",
    "connection_error": "连接错误",
    "js_required_page": "疑似需 JavaScript 渲染",
    "server_error": "服务器错误",
    "http_error": "其他 HTTP 错误",
    "invalid_url": "无效链接",
    "unknown": "未知状态",
}


def _now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat(timespec="seconds")


def _visible_text(text: str) -> str:
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def looks_like_js_page(result: FetchResult) -> bool:
    if result.content_type and "html" not in result.content_type.lower():
        return False
    text = result.text or ""
    lowered = text.lower()
    visible = _visible_text(text)
    if any(marker in lowered for marker in JS_MARKERS):
        return True
    root = any(marker in lowered for marker in ROOT_MARKERS)
    script_count = lowered.count("<script")
    return root and len(visible) < 300 and script_count >= 1
def _base_result(url: str, status: str, *, now: str | None = None,
                 http_status: int | None = None, final_url: str | None = None,
                 redirected: bool = False, js_page: bool = False,
                 error: str | None = None, content_type: str | None = None) -> dict[str, Any]:
    return {
        "url": url,
        "checked_at": now or _now_iso(),
        "status": status,
        "status_label": LINK_STATUS_LABELS.get(status, status),
        "http_status": http_status,
        "final_url": final_url or url,
        "redirected": bool(redirected),
        "js_page_detected": bool(js_page),
        "error": error,
        "content_type": content_type,
        "registration_open_claim": False,
        "note": "仅记录 HTTP 事实，不代表报名开放、资格有效或主办方确认。",
    }


def classify_fetch_result(result: FetchResult, *, now: str | None = None) -> dict[str, Any]:
    if result.timed_out:
        return _base_result(result.url, "timeout", now=now, final_url=result.final_url,
                            error=result.error or "请求超时", content_type=result.content_type)
    if result.error and result.status_code is None:
        return _base_result(result.url, "connection_error", now=now, final_url=result.final_url,
                            error=result.error, content_type=result.content_type)
    status = result.status_code
    if status is None:
        return _base_result(result.url, "connection_error", now=now, final_url=result.final_url,
                            error=result.error or "无 HTTP 状态", content_type=result.content_type)
    if 300 <= status < 400:
        return _base_result(result.url, "redirect", now=now, http_status=status,
                            final_url=result.final_url, redirected=True,
                            error=result.error, content_type=result.content_type)
    if status == 403:
        return _base_result(result.url, "forbidden", now=now, http_status=status,
                            final_url=result.final_url, redirected=result.redirected,
                            error=result.error, content_type=result.content_type)
    if status == 404:
        return _base_result(result.url, "not_found", now=now, http_status=status,
                            final_url=result.final_url, redirected=result.redirected,
                            error=result.error, content_type=result.content_type)
    if 400 <= status < 500:
        return _base_result(result.url, "http_error", now=now, http_status=status,
                            final_url=result.final_url, redirected=result.redirected,
                            error=result.error, content_type=result.content_type)
    if status >= 500:
        return _base_result(result.url, "server_error", now=now, http_status=status,
                            final_url=result.final_url, redirected=result.redirected,
                            error=result.error, content_type=result.content_type)
    if 200 <= status < 300:
        js_page = looks_like_js_page(result)
        if js_page:
            return _base_result(result.url, "js_required_page", now=now, http_status=status,
                                final_url=result.final_url, redirected=result.redirected,
                                js_page=True, content_type=result.content_type)
        if result.redirected:
            return _base_result(result.url, "redirect", now=now, http_status=status,
                                final_url=result.final_url, redirected=True,
                                content_type=result.content_type)
        return _base_result(result.url, "ok", now=now, http_status=status,
                            final_url=result.final_url, content_type=result.content_type)
    return _base_result(result.url, "unknown", now=now, http_status=status,
                        final_url=result.final_url, error=result.error,
                        content_type=result.content_type)


def check_link(url: str | None, fetcher: Any | None = None, *, now: str | None = None) -> dict[str, Any]:
    if not url:
        return _base_result("", "invalid_url", now=now, error="链接为空")
    try:
        parts = urlsplit(url)
    except ValueError:
        parts = None
    if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
        return _base_result(str(url), "invalid_url", now=now, error="仅接受 http/https 公开链接")
    checker = fetcher or HttpFetcher(timeout=10, retries=1, request_delay=0.5)
    try:
        result = checker.fetch(url)
    except Exception as exc:
        return _base_result(url, "connection_error", now=now, error=f"{type(exc).__name__}: {exc}")
    return classify_fetch_result(result, now=now)