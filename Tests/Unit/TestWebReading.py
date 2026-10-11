"""Offline behaviour of the user-specified URL reader.

Every case injects an httpx transport and a host resolver, so nothing here reaches
the public network. The resolver is what makes the SSRF checks testable: the reader
validates the addresses it would actually connect to, not the URL string alone.
"""

from __future__ import annotations

import httpx

from NoteAgent.BusinessModules.ChatAgent.WebReading import (
    HttpTrafilaturaReader,
    WebPageReader,
    WebPageResult,
)

PUBLIC_IP = "93.184.216.34"

ARTICLE_HTML = """<!doctype html>
<html><head><title>Python 的 GIL 是什么</title></head>
<body>
<nav><a href="/">首页</a><a href="/about">关于</a></nav>
<article>
<h1>Python 的 GIL 是什么</h1>
<p>全局解释器锁（GIL）是 CPython 用来保护解释器内部状态的互斥锁，它并不是 Python 语言规范的一部分，而是 CPython 这一具体实现的产物。</p>
<p>在任意时刻，只有一个线程能够持有 GIL 并执行 Python 字节码，因此即便在多核机器上，多个线程也无法真正并行地执行 Python 代码。</p>
<p>对于需要大量计算的场景，这通常意味着应该改用多进程，或者把计算密集部分交给 C 扩展以释放 GIL，从而让其他线程得以运行。</p>
<p>值得注意的是，输入输出密集的任务仍然能从多线程中获益，因为阻塞在 IO 上时线程会主动释放 GIL。</p>
</article>
<footer>版权所有 示例站点</footer>
</body></html>"""


async def _public_resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


async def _private_resolver(host: str) -> list[str]:
    return ["10.0.0.5"]


def _reader(handler, *, resolver=_public_resolver, **kwargs) -> HttpTrafilaturaReader:
    transport = httpx.MockTransport(handler)
    return HttpTrafilaturaReader(transport=transport, resolver=resolver, **kwargs)


def _html_response(html: str, *, status_code: int = 200, headers: dict | None = None) -> httpx.Response:
    base = {"content-type": "text/html; charset=utf-8"}
    if headers:
        base.update(headers)
    return httpx.Response(status_code, content=html.encode("utf-8"), headers=base)


async def test_extracts_article_title_and_body_not_navigation():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler).read("https://example.com/gil")

    assert isinstance(result, WebPageResult)
    assert result.status == "ok"
    assert result.url == "https://example.com/gil"
    assert result.final_url == "https://example.com/gil"
    assert result.title == "Python 的 GIL 是什么"
    assert "全局解释器锁" in result.content
    assert "无法真正并行" in result.content
    assert "首页" not in result.content
    assert result.error is None


async def test_follows_relative_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler).read("https://example.com/start")

    assert result.status == "ok"
    assert result.url == "https://example.com/start"
    assert result.final_url == "https://example.com/final"
    assert "全局解释器锁" in result.content


async def test_too_many_redirects_is_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    result = await _reader(handler, max_redirects=3).read("https://example.com/loop")

    assert result.status == "blocked"
    assert result.error
    assert "redirect" in result.error.lower() or "重定向" in result.error


async def test_login_page_reports_login_required():
    login = "<html><head><title>Sign in</title></head><body><h1>请登录以继续</h1><form>验证码</form></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(login)

    result = await _reader(handler).read("https://example.com/private")

    assert result.status == "login_required"
    assert result.content == ""
    assert result.error


async def test_empty_body_is_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response("<html><head></head><body></body></html>")

    result = await _reader(handler).read("https://example.com/empty")

    assert result.status in ("failed", "partial")
    assert result.content == ""
    assert result.error


async def test_non_html_is_unsupported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf"},
        )

    result = await _reader(handler).read("https://example.com/file.pdf")

    assert result.status == "unsupported"
    assert result.content == ""


async def test_timeout_is_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    result = await _reader(handler).read("https://example.com/slow")

    assert result.status == "failed"
    assert result.content == ""
    assert result.error


async def test_oversized_response_is_partial():
    filler = "<p>" + ("废话内容" * 4000) + "</p>"
    big = f"<html><head><title>大页面</title></head><body><article><h1>大页面</h1><p>正文开头关键句。</p>{filler}</article></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(big)

    result = await _reader(handler, max_response_bytes=2000).read("https://example.com/big")

    assert result.status == "partial"
    assert result.error


async def test_content_truncated_is_partial():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler, max_content_chars=10).read("https://example.com/gil")

    assert result.status == "partial"
    assert len(result.content) <= 10
    assert result.title == "Python 的 GIL 是什么"


async def test_loopback_target_is_blocked():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler).read("http://127.0.0.1/")

    assert result.status == "blocked"
    assert called["n"] == 0


async def test_private_domain_resolution_is_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler, resolver=_private_resolver).read("http://internal.example/notes")

    assert result.status == "blocked"
    assert result.content == ""


async def test_redirect_to_private_is_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/secret"})

    result = await _reader(handler).read("https://example.com/go")

    assert result.status == "blocked"
    assert result.content == ""


async def test_non_http_scheme_is_unsupported():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler).read("ftp://example.com/x")

    assert result.status == "unsupported"
    assert result.content == ""


async def test_credentials_in_url_are_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return _html_response(ARTICLE_HTML)

    result = await _reader(handler).read("http://user:pass@example.com/")

    assert result.status == "blocked"
    assert result.content == ""


async def test_http_error_status_is_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"})

    result = await _reader(handler).read("https://example.com/missing")

    assert result.status == "failed"
    assert result.url == "https://example.com/missing"


def test_protocol_accepts_a_fake_reader():
    class FakeReader:
        async def read(self, url: str) -> WebPageResult:
            return WebPageResult(
                url=url, final_url=url, status="ok", title="t", content="c", error=None
            )

    reader: WebPageReader = FakeReader()
    assert reader is not None
