"""Model settings persistence: load order, atomic writes, revisions, credentials."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from noteagent.bootstrap.settings import Settings
from noteagent.model_management.schemas import (
    ENV_PROFILE_ID,
    ChatProfile,
    ChatProfileIn,
    StoredModelSettings,
)
from noteagent.model_management.store import (
    ModelSettingsCorruptError,
    ModelSettingsRevisionError,
    ModelSettingsStore,
    initial_stored_settings,
)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Settings pointing every directory at tmp_path, so tests never touch the repo."""
    values: dict[str, object] = {
        "_env_file": None,
        "deepseek_api_key": SecretStr("env-secret"),
        "deepseek_api_base": "https://env.invalid/v1",
        "chat_model": "env-chat-model",
        "embedding_model": "intfloat/multilingual-e5-small",
        "chroma_collection": "env_collection",
        "notes_dir": tmp_path / "notes",
        "chroma_dir": tmp_path / "chroma",
        "log_dir": tmp_path / "logs",
        "embedding_cache_dir": tmp_path / "models",
        "model_settings_dir": tmp_path / "settings",
    }
    values.update(overrides)
    return Settings(**values)


def ui_profile(profile_id: str = "ui-1", **overrides) -> ChatProfile:
    """A user-created profile whose credential is stored in the settings file."""
    values: dict[str, object] = {
        "id": profile_id,
        "label": "本地兼容服务",
        "provider": "openai-compatible",
        "model": "qwen2.5",
        "base_url": "http://localhost:1234/v1",
        "api_key": SecretStr("ui-secret"),
        "context_window": 16384,
        "credential_source": "ui",
    }
    values.update(overrides)
    return ChatProfile(**values)


def test_load_returns_none_before_first_write(tmp_path):
    """A read-only start must not create a config file as a side effect."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)

    assert store.load() is None
    assert not store.path.exists()


def test_first_run_state_follows_the_environment(tmp_path):
    """Without a persisted file the env supplies the default profile and index state."""
    settings = make_settings(tmp_path)

    state = ModelSettingsStore(settings.model_settings_dir).load_effective(settings)

    assert state.revision == 0
    assert state.active_chat_profile_id == ENV_PROFILE_ID
    assert state.active_embedding is not None
    assert state.active_embedding.model_id == "intfloat/multilingual-e5-small"
    assert state.active_embedding.collection == "env_collection"
    # 初次状态只为描述现状，不算"已按新代码默认值改写指纹"。
    assert state.active_embedding.fingerprint is None
    assert state.profile_by_id(ENV_PROFILE_ID).credential_source == "env"


def test_persisted_active_wins_over_environment_model(tmp_path):
    """An existing file keeps its active pointer even if .env names another model."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)
    store.save(
        StoredModelSettings(
            chat_profiles=[ui_profile()],
            active_chat_profile_id="ui-1",
        )
    )

    state = store.load_effective(make_settings(tmp_path, chat_model="env-changed"))

    assert state.active_chat_profile_id == "ui-1"
    assert state.profile_by_id("ui-1").model == "qwen2.5"


def test_env_credential_is_not_copied_into_the_file(tmp_path):
    """The .env key must be referenced, not duplicated into the settings file."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)

    store.save(initial_stored_settings(settings))

    written = json.loads(store.path.read_text(encoding="utf-8"))
    assert written["chat_profiles"][0]["api_key"] == ""
    assert "env-secret" not in store.path.read_text(encoding="utf-8")
    # 加载时再从 Settings 解析回来，内存里必须是可用的凭据。
    reloaded = store.load_effective(settings)
    assert reloaded.profile_by_id(ENV_PROFILE_ID).api_key.get_secret_value() == "env-secret"


def test_ui_credential_round_trips_without_becoming_a_mask(tmp_path):
    """Regression: model_dump() would persist SecretStr as **********."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)

    store.save(StoredModelSettings(chat_profiles=[ui_profile()], active_chat_profile_id="ui-1"))
    reloaded = store.load_effective(settings)

    stored = reloaded.profile_by_id("ui-1")
    assert stored.api_key.get_secret_value() == "ui-secret"
    assert "**********" not in store.path.read_text(encoding="utf-8")


def test_public_view_never_exposes_the_key(tmp_path):
    """The API-facing shape carries has_api_key instead of the secret."""
    out = ui_profile().to_out()

    assert out.has_api_key is True
    assert "api_key" not in out.model_dump()
    assert "ui-secret" not in out.model_dump_json()


def test_save_bumps_revision_and_rejects_a_stale_writer(tmp_path):
    """A stale expected_revision must not overwrite a newer choice."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)

    first = store.save(StoredModelSettings(chat_profiles=[ui_profile()]))
    assert first.revision == 1

    with pytest.raises(ModelSettingsRevisionError):
        store.save(StoredModelSettings(chat_profiles=[ui_profile()]), expected_revision=0)

    second = store.save(StoredModelSettings(chat_profiles=[ui_profile()]), expected_revision=1)
    assert second.revision == 2


def test_failed_write_keeps_the_previous_file(tmp_path, monkeypatch):
    """An interrupted replace must not truncate or lose the stored configuration."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)
    store.save(StoredModelSettings(chat_profiles=[ui_profile()]))
    before = store.path.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("noteagent.model_management.store.os.replace", boom)
    with pytest.raises(OSError):
        store.save(StoredModelSettings(chat_profiles=[ui_profile("ui-2")]))

    assert store.path.read_text(encoding="utf-8") == before
    assert [p.name for p in settings.model_settings_dir.iterdir()] == ["settings.json"]


def test_corrupt_file_is_reported_and_preserved(tmp_path):
    """A broken file must fail loudly instead of being silently replaced."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)
    settings.model_settings_dir.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ModelSettingsCorruptError) as excinfo:
        store.load_effective(settings)

    assert str(store.path) in str(excinfo.value)
    assert store.path.read_text(encoding="utf-8") == "{not json"


def test_structurally_invalid_file_is_also_reported(tmp_path):
    """Valid JSON with a wrong shape is corruption too, not a first run."""
    settings = make_settings(tmp_path)
    store = ModelSettingsStore(settings.model_settings_dir)
    settings.model_settings_dir.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"chat_profiles": [{"label": "x"}]}), encoding="utf-8")

    with pytest.raises(ModelSettingsCorruptError):
        store.load()


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://user:pass@host/v1",
        "ftp://host/v1",
        "not-a-url",
    ],
)
def test_base_url_rejects_credentials_and_non_http(bad_url):
    """A URL carrying userinfo would leak a credential into logs and errors."""
    with pytest.raises(ValidationError):
        ChatProfileIn(label="x", provider="openai-compatible", model="m", base_url=bad_url)


def test_base_url_trailing_slash_is_normalized():
    """Stored URLs compare equal regardless of a trailing slash."""
    profile = ChatProfileIn(
        label="x", provider="openai-compatible", model="m", base_url="http://localhost:1234/v1/"
    )

    assert profile.base_url == "http://localhost:1234/v1"


def test_compatible_provider_requires_a_base_url():
    """There is no default host for an OpenAI-compatible service."""
    with pytest.raises(ValidationError):
        ChatProfileIn(label="x", provider="openai-compatible", model="m", base_url="")


def test_deepseek_may_omit_the_base_url():
    """DeepSeek has an SDK default endpoint, so an empty URL stays legal."""
    profile = ChatProfileIn(label="x", provider="deepseek", model="deepseek-chat", base_url="")

    assert profile.base_url == ""


def test_deepseek_rejects_unauthenticated_mode():
    """DeepSeek is a hosted service; it has no keyless deployment."""
    with pytest.raises(ValidationError):
        ChatProfileIn(
            label="x",
            provider="deepseek",
            model="deepseek-chat",
            base_url="",
            auth_mode="none",
        )


def test_clearing_and_setting_a_key_at_once_is_rejected():
    """The two intents contradict each other, so the form must not send both."""
    with pytest.raises(ValidationError):
        ChatProfileIn(
            label="x",
            provider="openai-compatible",
            model="m",
            base_url="http://localhost:1234/v1",
            api_key="new-key",
            clear_api_key=True,
        )


def test_blank_submitted_key_means_keep_the_stored_one():
    """An empty password box must not overwrite the saved credential."""
    profile = ChatProfileIn(
        label="x", provider="openai-compatible", model="m", base_url="http://localhost:1234/v1"
    )

    assert profile.provided_api_key() is None
