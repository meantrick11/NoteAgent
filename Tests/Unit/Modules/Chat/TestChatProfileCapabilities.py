import pytest
from pydantic import ValidationError

from pydantic import SecretStr

from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import ChatProfile, ChatProfileIn, StoredModelSettings, SCHEMA_VERSION
from NoteAgent.Modules.Models.Domain.Vo.ModelProfiles import merge_candidate
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore


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
