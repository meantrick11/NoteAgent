"""Legacy JSON import mapping and one-time archive behavior."""

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import (
    ActiveEmbedding,
    ChatProfile,
    StoredModelSettings,
)
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.LegacyModelSettingsImporter import LegacyModelSettingsImporter

from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

NOW = datetime(2026, 10, 20, tzinfo=UTC)


@pytest.fixture
def repo():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlModelConfigRepository(create_session_factory(engine))


def _settings() -> Settings:
    return Settings(_env_file=None, deepseek_api_key=SecretStr(""), chat_model="unused")


def _legacy_document() -> StoredModelSettings:
    return StoredModelSettings(
        schema_version=4,
        revision=0,
        chat_profiles=[
            ChatProfile(
                id="a",
                label="A",
                provider="deepseek",
                model="deepseek-chat",
                api_key=SecretStr("secret-a"),
                credential_source="ui",
                capabilities=["text", "vision"],
                text_enabled=True,
                verified_capabilities=["text", "vision"],
                capability_checked_at={"text": NOW, "vision": NOW},
            ),
            ChatProfile(
                id="b",
                label="B",
                provider="openai-compatible",
                model="qwen",
                base_url="http://localhost:1234/v1",
                api_key=SecretStr("secret-b"),
                credential_source="ui",
                capabilities=["text"],
                text_enabled=False,
            ),
        ],
        active_chat_profile_id="a",
        active_embedding=ActiveEmbedding(
            model_id="intfloat/multilingual-e5-small",
            collection="my_knowledge",
            resolved_revision=None,
            fingerprint=None,
        ),
    )


def _importer(repo, tmp_path):
    store = ModelSettingsStore(tmp_path)
    store.save(_legacy_document())
    return LegacyModelSettingsImporter(
        repository=repo,
        catalog=ProviderRegistry(),
        store=store,
        settings=_settings(),
    ), store


def test_import_maps_profiles_and_capabilities(repo, tmp_path):
    importer, _ = _importer(repo, tmp_path)
    result = importer.run()
    assert result.imported == 2
    assert repo.count_models() == 2
    active = repo.get_active_model()
    assert active is not None and active.id == "a"
    assert active.timeout_s == 60
    assert {item.capability for item in active.capabilities} == {"text", "vision"}
    vision = next(item for item in active.capabilities if item.capability == "vision")
    assert vision.verification == "verified"
    disabled = repo.get_model("b")
    text = next(item for item in disabled.capabilities if item.capability == "text")
    assert text.status == "disabled"


def test_import_archives_legacy_file_and_keeps_embedding_state(repo, tmp_path):
    importer, store = _importer(repo, tmp_path)
    assert importer.run().archived is True
    assert (tmp_path / "settings.pre-db.json").exists()
    live = store.load()
    assert live is not None
    assert live.chat_profiles == []
    assert live.active_chat_profile_id is None
    assert live.active_embedding is not None
    assert live.active_embedding.collection == "my_knowledge"


def test_import_is_idempotent(repo, tmp_path):
    importer, _ = _importer(repo, tmp_path)
    assert importer.run().imported == 2
    second = importer.run()
    assert second.skipped is True
    assert repo.count_models() == 2
