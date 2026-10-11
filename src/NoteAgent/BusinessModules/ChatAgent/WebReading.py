"""Read a user-specified URL and extract its article text.

First version: the server fetches the page itself (HTTPX) and extracts the body
locally (Trafilatura). The Agent tool talks to ``WebPageReader.read``, so a future
extraction API only has to implement the same interface and be substituted in
``RuntimeAssembler``; the tool name and result fields stay stable.

The reader validates the address it is about to connect to on every hop, so a
hostname that resolves to a private address (or a redirect that points at one) is
refused before any request is made. It never logs the page HTML or body.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

_logger = logging.getLogger(__name__)

WebStatus = Literal["ok", "partial", "login_required", "blocked", "unsupported", "failed"]

_ACCEPTED_CONTENT_TYPES = ("text/html", "application/xhtml")
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
# Short, specific phrases: a page that only mentions a login in passing still reads.
_LOGIN_MARKERS = (
    "captcha",
    "recaptcha",
    "cf-challenge",
    "just a moment",
    "人机验证",
    "验证码",
    "请登录",
    "登录以继续",
    "登录后继续",
    "sign in to continue",
    "log in to continue",
    "please log in",
    "enable javascript and cookies",
)


@dataclass(frozen=True)
class WebPageResult:
    """One URL's fetch outcome. ``content`` is empty unless a body was extracted."""

    url: str
    final_url: str | None
    status: WebStatus
    title: str | None
    content: str
    error: str | None


class WebPageReader(Protocol):
    """The only surface the chat tool depends on; swap implementations freely."""

    async def read(self, url: str) -> WebPageResult: ...


class _Blocked(Exception):
    """The target address is not allowed (private/loopback/internal)."""


class _Unsupported(Exception):
    """The URL cannot be read by this reader at all (scheme/type)."""


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_global


async def _default_resolve(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


class HttpTrafilaturaReader:
    """Fetch HTTP(S) pages with HTTPX and extract the body with Trafilatura."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable[[str], Awaitable[list[str]]] | None = None,
        max_redirects: int = 5,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 2_000_000,
        max_content_chars: int = 60_000,
    ) -> None:
        self._transport = transport
        self._resolver = resolver or _default_resolve
        self._max_redirects = max_redirects
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_response_bytes = max_response_bytes
        self._max_content_chars = max_content_chars

    async def read(self, url: str) -> WebPageResult:
        target = (url or "").strip()
        try:
            return await self._read(target)
        except _Blocked as exc:
            return self._result(target, None, "blocked", None, "", str(exc))
        except _Unsupported as exc:
            return self._result(target, None, "unsupported", None, "", str(exc))
        except httpx.TimeoutException:
            return self._result(target, None, "failed", None, "", "请求超时，未能读取网页")
        except httpx.HTTPError as exc:
            return self._result(target, None, "failed", None, "", f"网络请求失败：{exc.__class__.__name__}")

    async def _read(self, url: str) -> WebPageResult:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https"):
            raise _Unsupported("仅支持 http/https 链接")
        if parsed.username or parsed.password:
            raise _Blocked("链接中不允许包含凭据")

        current = url
        async with httpx.AsyncClient(
            transport=self._transport, follow_redirects=False, timeout=self._timeout
        ) as client:
            for _hop in range(self._max_redirects + 1):
                host = urlsplit(current).hostname or ""
                await self._ensure_public(host)
                async with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            return self._result(url, None, "failed", None, "", "重定向缺少目标地址")
                        current = urljoin(current, location)
                        continue
                    if response.status_code in (401, 403, 429):
                        return self._result(
                            url, str(response.url), "blocked", None, "",
                            f"网页拒绝访问（HTTP {response.status_code}）",
                        )
                    if response.status_code >= 400:
                        return self._result(
                            url, str(response.url), "failed", None, "",
                            f"网页返回 HTTP {response.status_code}",
                        )
                    content_type = (response.headers.get("content-type") or "").lower()
                    if content_type and not any(t in content_type for t in _ACCEPTED_CONTENT_TYPES):
                        raise _Unsupported("网页不是 HTML 正文页")
                    body, truncated = await self._read_capped(response)
                    return self._extract(
                        url, str(response.url), body, content_type, truncated
                    )
            return self._result(url, current, "blocked", None, "", "重定向次数过多")

    async def _ensure_public(self, host: str) -> None:
        """Validate the address set this host resolves to, before connecting."""
        name = host.strip().strip(".").lower()
        if not name:
            raise _Unsupported("链接缺少主机名")
        if name == "localhost" or name.endswith((".localhost", ".local", ".internal")):
            raise _Blocked("目标指向本机或内网主机")
        try:
            literal = ipaddress.ip_address(name)
        except ValueError:
            literal = None
        if literal is not None:
            if not _is_public_ip(literal):
                raise _Blocked("目标是非公网地址")
            return
        addresses = await self._resolver(name)
        if not addresses:
            raise _Blocked("无法解析目标主机")
        for address in addresses:
            try:
                resolved = ipaddress.ip_address(address)
            except ValueError:
                raise _Blocked("目标主机解析到无效地址")
            if not _is_public_ip(resolved):
                raise _Blocked("目标主机解析到非公网地址")

    async def _read_capped(self, response: httpx.Response) -> tuple[bytes, bool]:
        """Read at most ``max_response_bytes``; report whether the cap was hit."""
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._max_response_bytes:
                keep = len(chunk) - (total - self._max_response_bytes)
                chunks.append(chunk[:keep])
                _logger.info("web read truncated bytes=%d", self._max_response_bytes)
                return b"".join(chunks), True
            chunks.append(chunk)
        return b"".join(chunks), False

    def _extract(
        self,
        requested: str,
        final: str,
        body: bytes,
        content_type: str,
        truncated: bool,
    ) -> WebPageResult:
        html = body.decode(_charset_of(content_type), errors="replace")
        lowered = html.lower()
        if any(marker in lowered for marker in _LOGIN_MARKERS):
            return self._result(
                requested, final, "login_required", None, "",
                "页面需要登录或人机验证，未能读取正文",
            )
        extracted = trafilatura.extract(
            html,
            url=final,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            include_tables=True,
        )
        if not extracted:
            if truncated:
                return self._result(
                    requested, final, "partial", None, "",
                    "网页响应过大，只读取了开头且未能提取正文",
                )
            return self._result(requested, final, "failed", None, "", "未能从页面提取正文")
        payload = json.loads(extracted)
        title = payload.get("title") or None
        text = (payload.get("text") or "").strip()
        if not text:
            return self._result(requested, final, "failed", title, "", "网页正文为空")
        if len(text) > self._max_content_chars:
            text = text[: self._max_content_chars]
            return self._result(
                requested, final, "partial", title, text, "网页正文过长，已截断"
            )
        if truncated:
            return self._result(
                requested, final, "partial", title, text, "网页响应过大，仅读取了前一部分"
            )
        return self._result(requested, final, "ok", title, text, None)

    def _result(
        self,
        url: str,
        final_url: str | None,
        status: WebStatus,
        title: str | None,
        content: str,
        error: str | None,
    ) -> WebPageResult:
        return WebPageResult(
            url=url,
            final_url=final_url,
            status=status,
            title=title,
            content=content,
            error=error,
        )


def _charset_of(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip().strip('"')
    return "utf-8"


__all__ = ["HttpTrafilaturaReader", "WebPageReader", "WebPageResult", "WebStatus"]
