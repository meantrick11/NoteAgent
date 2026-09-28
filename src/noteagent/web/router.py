"""页面路由：把 SPA 外壳与旧的单模板页面分开管理。

只有 SPA_PAGE_PATHS 里的地址返回 HTML；未知的 API 路径、不存在的 JS/CSS 一律 404，
不能被兜底 HTML 吞掉。业务路由仍在各自的 router 里（chat／notes／model-settings）。

FRONTEND_MODE 决定走哪一套：
  legacy —— 旧模板继续服务 "/" 与 "/documents"，其余入口按旧地址跳转（回退模式）；
  vue    —— 六个页面地址都返回 Vite 产物，产物缺失时 503 并给出构建提示。
"""

import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from noteagent.web import read_home_html, read_spa_html

_logger = logging.getLogger(__name__)

router = APIRouter()

# 页面白名单。必须与 frontend/src/shared/navigation.ts 的入口一一对应；
# 下面按这份名单注册路由，列表与路由表不会各自漂移。
SPA_PAGE_PATHS = ("/", "/assistant", "/records", "/library", "/settings", "/documents")

# legacy 模式下没有旧实现的入口回落到哪。
_LEGACY_REDIRECTS = {"/assistant": "/", "/records": "/", "/settings": "/", "/library": "/documents"}

_MISSING_BUILD_HINT = (
    "前端产物未构建：frontend/dist 里没有 index.html。\n"
    "请先执行 `npm --prefix frontend ci && npm --prefix frontend run build`，"
    "或把 FRONTEND_MODE 设为 legacy 使用旧页面。"
)


def _frontend_mode(request: Request) -> str:
    """Which frontend the app was started with; unknown values fall back to legacy."""
    mode = getattr(request.app.state.container.settings, "frontend_mode", "legacy")
    return "vue" if mode == "vue" else "legacy"


def _spa_shell() -> HTMLResponse:
    """Serve the built SPA shell, or fail loudly when it was never built."""
    html = read_spa_html()
    if html is None:
        _logger.error("frontend_mode=vue but web/dist/index.html is missing")
        raise HTTPException(status_code=503, detail=_MISSING_BUILD_HINT)
    return HTMLResponse(html)


def _resolve_page(path: str, request: Request) -> HTMLResponse | RedirectResponse:
    """Resolve one page address for the configured frontend mode."""
    if _frontend_mode(request) == "vue":
        return _spa_shell()
    legacy_path = _LEGACY_REDIRECTS.get(path)
    if legacy_path:
        return RedirectResponse(url=legacy_path, status_code=307)
    return HTMLResponse(read_home_html())


def _page_handler(path: str) -> Callable[[Request], object]:
    """Build the handler for one page address."""

    async def handler(request: Request) -> HTMLResponse | RedirectResponse:
        return _resolve_page(path, request)

    handler.__doc__ = f"Serve the {path} page for the configured frontend mode."
    return handler


for _path in SPA_PAGE_PATHS:
    router.add_api_route(
        _path,
        _page_handler(_path),
        methods=["GET"],
        response_class=HTMLResponse,
        # 返回的是两种 Response 之一，不能让 FastAPI 从注解推导响应模型。
        response_model=None,
        name=f"page:{_path}",
    )
