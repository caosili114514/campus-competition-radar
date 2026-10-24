"""带超时、重试、请求间隔和明确 User-Agent 的公开页面抓取器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import gzip
from pathlib import Path
import re
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .dates import TZ

DEFAULT_USER_AGENT = (
    "CampusCompetitionRadar/1.0 (public-interest competition notice collector; "
    "respectful crawling; contact: repository maintainer)"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None
@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    text: str = ""
    content_type: str | None = None
    elapsed_seconds: float = 0.0
    attempts: int = 1
    redirected: bool = False
    timed_out: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 300


def _header_value(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value is not None:
            return str(value)
        value = headers.get(name.lower())
        return str(value) if value is not None else None
    except AttributeError:
        return None


def decode_body(body: bytes, content_type: str | None = None) -> str:
    if body.startswith(b"\x1f\x8b"):
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    charset = None
    if content_type:
        match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
    if not charset:
        head = body[:4096].decode("ascii", errors="ignore")
        match = re.search(r"<meta[^>]+charset\s*=\s*[\"']?([\w-]+)", head, re.I)
        if match:
            charset = match.group(1)
    for encoding in (charset, "utf-8-sig", "gb18030"):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")
class HttpFetcher:
    """标准库 HTTP 抓取器。不会提交登录信息或绕过验证码。"""

    def __init__(self, *, timeout: float = 15.0, retries: int = 2,
                 request_delay: float = 1.0,
                 user_agent: str = DEFAULT_USER_AGENT,
                 opener: Any | None = None,
                 sleep_fn: Any = time.sleep,
                 max_bytes: int = 5 * 1024 * 1024,
                 follow_redirects: bool = True):
        self.timeout = max(0.1, float(timeout))
        self.retries = max(0, int(retries))
        self.request_delay = max(0.0, float(request_delay))
        self.user_agent = user_agent.strip() or DEFAULT_USER_AGENT
        self.sleep_fn = sleep_fn
        self.max_bytes = max(1024, int(max_bytes))
        self._last_request_at: float | None = None
        if opener is not None:
            self._opener = opener
        elif follow_redirects:
            self._opener = build_opener()
        else:
            self._opener = build_opener(_NoRedirectHandler())

    def set_request_delay(self, seconds: float) -> None:
        """按来源动态设置最小请求间隔。"""
        self.request_delay = max(0.0, float(seconds))

    def _wait_for_interval(self) -> None:
        if self._last_request_at is None:
            return
        wait = self.request_delay - (time.monotonic() - self._last_request_at)
        if wait > 0:
            self.sleep_fn(wait)

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        started = time.monotonic()
        if not isinstance(url, str) or urlsplit(url).scheme.lower() not in ("http", "https"):
            return FetchResult(url=str(url), final_url=str(url), error="仅允许 http/https 公开地址")
        request_headers = dict(DEFAULT_HEADERS)
        request_headers["User-Agent"] = self.user_agent
        if headers:
            request_headers.update(headers)
        last: FetchResult | None = None
        total_attempts = self.retries + 1
        for attempt in range(1, total_attempts + 1):
            self._wait_for_interval()
            self._last_request_at = time.monotonic()
            try:
                request = Request(url, headers=request_headers, method="GET")
                with self._opener.open(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    body = response.read(self.max_bytes + 1)[:self.max_bytes]
                    headers_map = {str(k).lower(): str(v) for k, v in response.headers.items()}
                    content_type = _header_value(response.headers, "Content-Type")
                    final_url = response.geturl()
                    result = FetchResult(
                        url=url, final_url=final_url, status_code=int(status),
                        headers=headers_map, body=body, text=decode_body(body, content_type),
                        content_type=content_type,
                        elapsed_seconds=round(time.monotonic() - started, 3),
                        attempts=attempt,
                        redirected=final_url != url,
                    )
                    return result
            except HTTPError as exc:
                body = b""
                try:
                    body = exc.read(self.max_bytes + 1)[:self.max_bytes]
                except Exception:
                    pass
                content_type = _header_value(exc.headers, "Content-Type")
                result = FetchResult(
                    url=url, final_url=exc.geturl() or url, status_code=int(exc.code),
                    headers={str(k).lower(): str(v) for k, v in (exc.headers or {}).items()},
                    body=body, text=decode_body(body, content_type), content_type=content_type,
                    elapsed_seconds=round(time.monotonic() - started, 3), attempts=attempt,
                    redirected=(exc.geturl() or url) != url,
                    error=f"HTTP {exc.code}",
                )
                result.error = None if 300 <= result.status_code < 500 else result.error
                last = result
            except (socket.timeout, TimeoutError) as exc:
                last = FetchResult(url=url, final_url=url, attempts=attempt,
                                   elapsed_seconds=round(time.monotonic() - started, 3),
                                   timed_out=True, error=f"请求超时: {exc}")
            except URLError as exc:
                reason = getattr(exc, "reason", exc)
                timed_out = isinstance(reason, (socket.timeout, TimeoutError))
                last = FetchResult(url=url, final_url=url, attempts=attempt,
                                   elapsed_seconds=round(time.monotonic() - started, 3),
                                   timed_out=timed_out,
                                   error=f"连接失败: {reason}")
            except Exception as exc:  # 网络栈异常不应终止整批采集。
                last = FetchResult(url=url, final_url=url, attempts=attempt,
                                   elapsed_seconds=round(time.monotonic() - started, 3),
                                   error=f"抓取异常: {type(exc).__name__}: {exc}")
            should_retry = last is not None and (
                last.error is not None or (last.status_code is not None and last.status_code >= 500)
            )
            if not should_retry or attempt >= total_attempts:
                break
        return last or FetchResult(url=url, final_url=url, error="未知抓取错误")
class FixtureFetcher:
    """离线测试/演示抓取器：只从指定 fixtures 目录读取，不联网。"""

    def __init__(self, fixtures_dir: str | Path, *, user_agent: str = DEFAULT_USER_AGENT):
        self.root = Path(fixtures_dir).resolve()
        self.user_agent = user_agent

    def _resolve_path(self, url: str) -> Path:
        text = unquote(str(url)).strip()
        if text.startswith("fixture://"):
            text = text[len("fixture://"):]
        elif text.startswith("fixture:"):
            text = text[len("fixture:"):]
        else:
            raise ValueError("fixture 来源只能使用 fixture:// 地址")
        relative = text.lstrip("/\\")
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("fixture 路径越界") from exc
        return target

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        try:
            path = self._resolve_path(url)
        except ValueError as exc:
            return FetchResult(url=url, final_url=url, error=str(exc))
        if not path.is_file():
            return FetchResult(url=url, final_url=url,
                               error=f"fixture 文件不存在: {path.name}")
        body = path.read_bytes()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".htm": "text/html; charset=utf-8",
            ".xml": "application/xml; charset=utf-8",
            ".rss": "application/rss+xml; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FetchResult(
            url=url, final_url=url, status_code=200,
            headers={"content-type": content_type}, body=body,
            text=decode_body(body, content_type), content_type=content_type,
            attempts=1,
        )