"""页面路由与前端形态的集成测试。

不要求 Node：vue 模式用临时目录里的 index.html 代替真实构建产物，
真实产物的托管由浏览器验收与镜像构建覆盖。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import noteagent.web as web
from noteagent.bootstrap.app import create_app
from noteagent.bootstrap.settings import Settings
from noteagent.notes.repository import FileNoteRepository
from noteagent.web import read_home_html
from noteagent.web.router import SPA_PAGE_PATHS

from test_app import FakeAgent, _container, _sqlite_history

_SPA_SHELL = '<!DOCTYPE html><html><body><div id="app"></div></body></html>'


def _client(tmp_path: Path, mode: str) -> TestClient:
    """A TestClient wired with the same fakes the other integration tests use."""
    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
        frontend_mode=mode,
    )
    engine, history = _sqlite_history()
    container = _container(
        settings, FileNoteRepository(tmp_path), engine, history, FakeAgent()
    )
    return TestClient(create_app(container))


def _install_fake_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the SPA reader at a temp dist so no npm build is needed."""
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text(_SPA_SHELL, encoding="utf-8")
    monkeypatch.setattr(web, "SPA_INDEX", index)
    monkeypatch.setattr(web, "DIST_DIR", dist)


def test_default_frontend_mode_is_legacy():
    assert Settings().frontend_mode == "legacy"


class TestLegacyMode:
    """回退模式：旧页面照旧可用，新入口按旧地址跳转。"""

    def test_root_serves_the_legacy_template(self, tmp_path: Path):
        response = _client(tmp_path, "legacy").get("/")
        assert response.status_code == 200
        assert response.text == read_home_html()

    def test_documents_serves_the_legacy_template(self, tmp_path: Path):
        response = _client(tmp_path, "legacy").get("/documents")
        assert response.status_code == 200
        assert response.text == read_home_html()

    def test_new_entry_points_redirect_to_their_legacy_equivalent(self, tmp_path: Path):
        client = _client(tmp_path, "legacy")
        for path, expected in [
            ("/assistant", "/"),
            ("/records", "/"),
            ("/settings", "/"),
            ("/library", "/documents"),
        ]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 307, path
            assert response.headers["location"] == expected, path

    def test_unknown_value_falls_back_to_legacy(self, tmp_path: Path):
        # 配置里写了非法值（这里绕过 Literal 直接改对象）时按 legacy 处理，不至于打不开页面。
        client = _client(tmp_path, "legacy")
        client.app.state.container.settings.frontend_mode = "something-else"  # type: ignore[assignment]
        assert client.get("/").text == read_home_html()


class TestVueMode:
    """vue 模式：六个页面地址都返回 SPA 外壳。"""

    def test_every_page_path_serves_the_spa_shell(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _install_fake_dist(tmp_path, monkeypatch)
        client = _client(tmp_path, "vue")
        for path in SPA_PAGE_PATHS:
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.text == _SPA_SHELL, path

    def test_missing_build_answers_503_without_serving_the_legacy_page(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        missing = tmp_path / "not-built" / "index.html"
        monkeypatch.setattr(web, "SPA_INDEX", missing)
        monkeypatch.setattr(web, "DIST_DIR", missing.parent)
        client = _client(tmp_path, "vue")
        for path in SPA_PAGE_PATHS:
            response = client.get(path)
            assert response.status_code == 503, path
            # 不静默显示旧页假装迁移成功。
            assert read_home_html() not in response.text, path
            detail = response.json()["detail"]
            assert "index.html" in detail, path
            assert "run build" in detail, path

    def test_whitelist_paths_are_all_routable(self, tmp_path: Path):
        """页面白名单里的每个地址都真的注册了，不会掉进 404。"""
        client = _client(tmp_path, "legacy")
        for path in SPA_PAGE_PATHS:
            response = client.get(path, follow_redirects=False)
            assert response.status_code in (200, 307), path


class TestNotFound:
    """未知地址必须 404，不能被兜底 HTML 吞掉。"""

    def test_unknown_api_path_is_not_html(self, tmp_path: Path):
        response = _client(tmp_path, "legacy").get("/api/no-such-thing")
        assert response.status_code == 404
        assert not response.headers["content-type"].startswith("text/html")

    def test_unknown_page_path_is_not_html(self, tmp_path: Path):
        # 页面白名单之外不返回 HTML：/documents/extra 不是页面。
        response = _client(tmp_path, "legacy").get("/documents/extra")
        assert response.status_code == 404
        assert not response.headers["content-type"].startswith("text/html")

    def test_missing_frontend_asset_is_not_html(self, tmp_path: Path):
        response = _client(tmp_path, "legacy").get("/ui-assets/assets/missing.js")
        assert response.status_code == 404
        assert not response.headers["content-type"].startswith("text/html")
