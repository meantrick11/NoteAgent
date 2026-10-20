"""Model configuration use cases with deterministic probes and SQLite storage."""

import pytest

from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import find_capability
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    ProtocolUnsupportedError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService

from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

SENTINEL = object()


@pytest.fixture
def repo():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlModelConfigRepository(create_session_factory(engine))


def _config(model_id: str = "a", **changes) -> ModelConfig:
    values = {
        "id": model_id,
        "label": "A",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "secret",
        "max_tokens": 1024,
    }
    values.update(changes)
    return ModelConfig(**values)


def _service(repo, *, text=None, vision=None):
    text = text or ChatProbeResult(streaming=True, tool_calling=True)
    vision = vision if vision is not None else True

    async def probe_text(_client):
        return text

    async def probe_vision(_client):
        return vision

    return ModelConfigService(
        repository=repo,
        catalog=ProviderRegistry(),
        probe_text=probe_text,
        probe_vision=probe_vision,
        client_factory=lambda _config, _spec: SENTINEL,
    )


def test_create_injects_text_and_keeps_model_inactive(repo):
    service = _service(repo)
    created = service.create(_config())
    assert created.is_active is False
    assert created.revision == 1
    assert find_capability(created.capabilities, "text").verification == "unverified"


def test_create_rejects_unknown_provider(repo):
    service = _service(repo)
    with pytest.raises(Exception, match="未知的 Provider"):
        service.create(_config(provider="missing"))


@pytest.mark.asyncio
async def test_verify_text_success_and_failure_are_persisted(repo):
    service = _service(repo)
    service.create(_config())
    verified = await service.verify_capability("a", "text", 1)
    text = find_capability(verified.capabilities, "text")
    assert text.verification == "verified"
    assert text.evidence == {"streaming": True, "tool_calling": True}

    failing = _service(repo, text=ChatProbeResult(streaming=False, tool_calling=False))
    with pytest.raises(ProtocolUnsupportedError):
        await failing.verify_capability("a", "text", 2)
    text = find_capability(repo.get_model("a").capabilities, "text")
    assert text.verification == "failed"


@pytest.mark.asyncio
async def test_verify_vision_requires_text_and_records_failure(repo):
    service = _service(repo, vision=False)
    service.create(_config())
    with pytest.raises(ProtocolUnsupportedError):
        await service.verify_capability("a", "vision", 1)
    stored = repo.get_model("a")
    assert find_capability(stored.capabilities, "text").verification == "verified"
    assert find_capability(stored.capabilities, "vision").verification == "failed"


@pytest.mark.asyncio
async def test_verify_vision_success_and_disable_clears_evidence(repo):
    service = _service(repo)
    service.create(_config())
    verified = await service.verify_capability("a", "vision", 1)
    assert find_capability(verified.capabilities, "vision").verification == "verified"

    disabled = service.disable_capability("a", "vision", 2)
    vision = find_capability(disabled.capabilities, "vision")
    assert vision.status == "disabled"
    assert vision.verification == "unverified"
    assert vision.probe_version is None


@pytest.mark.asyncio
async def test_pinned_client_requires_matching_revision_and_vision(repo):
    service = _service(repo)
    service.create(_config())
    await service.verify_capability("a", "vision", 1)
    assert service.build_client_for_parse("a", 2) is SENTINEL
    with pytest.raises(RevisionConflictError):
        service.build_client_for_parse("a", 1)
    # A text-only parse path does not require a verified vision row.
    assert service.build_client_for_parse("a", 2, vision=False) is SENTINEL


def test_update_rejects_stale_revision(repo):
    service = _service(repo)
    service.create(_config())
    service.update("a", 1, _config(label="B"))
    with pytest.raises(RevisionConflictError):
        service.update("a", 1, _config(label="C"))
