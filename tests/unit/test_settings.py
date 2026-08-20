from pathlib import Path

import pytest
from pydantic import SecretStr

from noteagent.bootstrap.settings import Settings, project_root


def test_project_root_is_repo():
    assert (project_root() / "pyproject.toml").exists()


def test_relative_paths_resolve_under_project_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NOTES_DIR", raising=False)
    settings = Settings(notes_dir=Path("notes"))
    assert settings.notes_dir.is_absolute()
    assert settings.notes_dir == (project_root() / "notes").resolve()


def test_secret_key_not_in_repr():
    settings = Settings(deepseek_api_key=SecretStr("sk-secret-value"))
    rendered = repr(settings)
    assert "sk-secret-value" not in rendered
    assert "**********" in rendered or "SecretStr" in rendered


def test_env_override_notes_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("NOTES_DIR", str(tmp_path))
    settings = Settings()
    assert settings.notes_dir == tmp_path.resolve()


def test_embedding_cache_dir_is_absolute():
    settings = Settings()
    assert settings.embedding_model
    assert settings.embedding_cache_dir.is_absolute()


def test_env_override_embedding_model_and_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "hf-cache"))
    monkeypatch.setenv("EMBEDDING_LOCAL_FILES_ONLY", "true")
    settings = Settings()
    assert settings.embedding_model == "BAAI/bge-small-zh-v1.5"
    assert settings.embedding_cache_dir == (tmp_path / "hf-cache").resolve()
    assert settings.embedding_local_files_only is True


def test_env_override_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:secret@127.0.0.1:5432/noteagent",
    )
    settings = Settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_url.endswith("/noteagent")
