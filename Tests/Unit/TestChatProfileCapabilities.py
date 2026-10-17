import pytest
from types import SimpleNamespace
from pydantic import ValidationError

from pydantic import SecretStr

from NoteAgent.BusinessModules.ModelSettings.ModelContracts import ChatProfile, ChatProfileIn, StoredModelSettings, SCHEMA_VERSION
from NoteAgent.BusinessModules.ModelSettings.ModelProfiles import merge_candidate
from NoteAgent.BusinessModules.ModelSettings.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.AppBootstrap.SourceVision import vision_factory
from NoteAgent.BusinessModules.SourceFiles.SourceFileContracts import ParseError


def test_legacy_profile_defaults_to_text_only():
    profile = ChatProfile.model_validate({
        "id": "old", "label": "old", "provider": "deepseek", "model": "chat"
    })
    assert profile.capabilities == ["text"]
    assert profile.to_out().capabilities == ["text"]


def test_vision_tag_survives_profile_merge():
    submitted = ChatProfileIn(
        label="vision", provider="openai-compatible", model="vision-model",
        base_url="http://localhost:1234/v1", auth_mode="none",
        capabilities=["text", "vision"],
    )
    saved = merge_candidate(submitted, None, profile_id="new")
    assert saved.capabilities == ["text", "vision"]
    assert saved.to_out().capabilities == ["text", "vision"]


def test_chat_profile_requires_text_capability():
    with pytest.raises(ValidationError):
        ChatProfileIn(
            label="vision", provider="deepseek", model="chat",
            capabilities=["vision"],
        )


def test_vision_label_and_key_survive_settings_save(tmp_path):
    store = ModelSettingsStore(tmp_path)
    profile = ChatProfile(id="vision", label="vision", provider="openai-compatible",
                          model="vision-model", base_url="http://localhost:1234/v1",
                          api_key=SecretStr("secret"), capabilities=["text", "vision"])
    saved = store.save(StoredModelSettings(schema_version=1, chat_profiles=[profile]))
    loaded = store.load()
    assert saved.schema_version == SCHEMA_VERSION
    assert loaded.chat_profiles[0].capabilities == ["text", "vision"]
    assert loaded.chat_profiles[0].api_key.get_secret_value() == "secret"


def test_vision_parse_rejects_missing_tag_or_changed_revision():
    text_only = ChatProfile(id="p", label="text", provider="deepseek", model="chat")
    source = SimpleNamespace(media_type="image/png", parse_profile_id="p", parse_profile_revision=1)
    store = SimpleNamespace(load_effective=lambda _settings: StoredModelSettings(
        revision=1, chat_profiles=[text_only]))
    with pytest.raises(ParseError):
        vision_factory(source, store, None)
    vision = text_only.model_copy(update={"capabilities": ["text", "vision"]})
    changed = SimpleNamespace(load_effective=lambda _settings: StoredModelSettings(
        revision=2, chat_profiles=[vision]))
    with pytest.raises(ParseError):
        vision_factory(source, changed, None)
