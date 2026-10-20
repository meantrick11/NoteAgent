"""Repository contract tests on in-memory SQLite (no PostgreSQL required)."""

from datetime import UTC, datetime

import pytest

from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    initial_capabilities,
    text_verified,
    vision_verified,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    ActiveModelProtectedError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository

# Registers the two tables on the shared metadata.
from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

NOW = datetime(2026, 10, 20, tzinfo=UTC)


@pytest.fixture
def repo():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlModelConfigRepository(create_session_factory(engine))


def _config(
    model_id: str = "m1",
    *,
    label: str = "Model",
    model: str = "deepseek-chat",
    is_active: bool = False,
):
    return ModelConfig(
        id=model_id,
        label=label,
        provider="deepseek",
        model=model,
        api_key="secret",
        is_active=is_active,
        capabilities=text_verified(
            initial_capabilities(),
            evidence={"streaming": True, "tool_calling": True},
            checked_at=NOW,
        ),
    )


def test_create_and_read_model(repo):
    created = repo.create_model(_config())
    assert created.revision == 1
    assert created.is_active is False
    assert repo.count_models() == 1
    stored = repo.get_model("m1")
    assert stored is not None
    assert stored.model == "deepseek-chat"
    assert stored.capabilities[0].verification == "verified"
    assert [item.id for item in repo.list_models()] == ["m1"]


def test_update_preserves_verification_for_same_connection(repo):
    repo.create_model(_config())
    updated = repo.update_model("m1", 1, _config(label="Renamed"))
    assert updated.revision == 2
    assert updated.label == "Renamed"
    assert updated.capabilities[0].verification == "verified"


def test_connection_change_invalidates_verification(repo):
    repo.create_model(_config())
    updated = repo.update_model("m1", 1, _config(model="deepseek-reasoner"))
    assert updated.model == "deepseek-reasoner"
    assert updated.capabilities[0].verification == "unverified"
    assert updated.capabilities[0].probe_version is None


def test_update_with_stale_revision_conflicts(repo):
    repo.create_model(_config())
    repo.update_model("m1", 1, _config(label="First"))
    with pytest.raises(RevisionConflictError):
        repo.update_model("m1", 1, _config(label="Second"))


def test_activate_switches_only_one_active_row(repo):
    repo.create_model(_config("a", label="A"))
    repo.create_model(_config("b", label="B"))
    active_a = repo.activate_model("a", 1)
    assert active_a.is_active is True
    active_b = repo.activate_model("b", 1)
    assert active_b.is_active is True
    assert repo.get_model("a").is_active is False
    assert repo.get_active_model().id == "b"


def test_active_model_cannot_be_edited_or_deleted(repo):
    repo.create_model(_config("a"))
    repo.activate_model("a", 1)
    with pytest.raises(ActiveModelProtectedError):
        repo.update_model("a", 2, _config("a", label="Nope"))
    with pytest.raises(ActiveModelProtectedError):
        repo.delete_model("a", 2)


def test_activate_can_save_a_full_config(repo):
    repo.create_model(_config("a", label="Old"))
    saved = _config("a", label="New")
    activated = repo.activate_model("a", 1, saved)
    assert activated.label == "New"
    assert activated.is_active is True
    assert activated.revision == 2


def test_replace_capabilities_adds_vision(repo):
    repo.create_model(_config("a"))
    records = text_verified(
        initial_capabilities(), evidence={"streaming": True}, checked_at=NOW
    )
    records = vision_verified(records, evidence={"challenge": "2x6"}, checked_at=NOW)
    updated = repo.replace_capabilities("a", 1, records)
    assert updated.revision == 2
    assert {item.capability for item in updated.capabilities} == {"text", "vision"}


def test_import_is_idempotent_and_sets_active(repo):
    imported = repo.import_models([_config("a"), _config("b")], "b")
    assert imported == 2
    assert repo.get_active_model().id == "b"
    assert repo.import_models([_config("c")], "c") == 0
    assert repo.get_active_model().id == "b"
