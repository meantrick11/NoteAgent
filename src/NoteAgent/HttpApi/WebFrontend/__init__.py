from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
# 外置 CSS/JS 的目录；FastAPI 必须显式 mount，模板不会自动提供静态资源路由。
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Vite 构建产物目录。dist 不入库，由 frontend/ 的 npm run build 或镜像构建阶段生成。
DIST_DIR = Path(__file__).resolve().parent / "dist"

SPA_INDEX = DIST_DIR / "index.html"


# 获取初始页的窗口
def read_home_html() -> str:
    """Load the legacy home page template from disk."""
    return (TEMPLATES_DIR / "home.html").read_text(encoding="utf-8")


def read_spa_html() -> str | None:
    """Load the built Vue shell, or None when the frontend has not been built.

    Returning None lets the caller answer 503 with a build hint instead of quietly
    falling back to the legacy page, which would look like a successful migration.
    """
    if not SPA_INDEX.is_file():
        return None
    return SPA_INDEX.read_text(encoding="utf-8")
