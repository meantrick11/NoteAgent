"""Activation ordering: probe, build, commit, publish."""

import pytest

from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import ProtocolUnsupportedError, RevisionConflictError
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.ModelActivationService import ModelActivationService
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService

from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

AGENT = object()
RETRIEVAL = object()


class _Assembler:
    def build_agent(self, *, model, retrieval):
        assert retrieval is RETRIEVAL
        return AGENT


class _Publisher:
    def __init__(self):
        self.calls = []

    def publish(self, *, model, agent, retrieval):
        self.calls.append((model, agent, retrieval))


@pytest.fixture
def repo():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlModelConfigRepository(create_session_factory(engine))


def _config(model_id="a", **changes):
    values = {
        "id": model_id,
        "label": "A",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "secret",
    }
    values.update(changes)
    return ModelConfig(**values)


def _services(repo, *, probe_result=None):
    probe_result = probe_result or ChatProbeResult(streaming=True, tool_calling=True)

    async def probe_text(_client):
        return probe_result

    config_service = ModelConfigService(
        repository=repo,
        catalog=ProviderRegistry(),
        probe_text=probe_text,
        client_factory=lambda _config, _spec: object(),
    )
    publisher = _Publisher()
    activation = ModelActivationService(
        repository=repo,
        config_service=config_service,
        catalog=ProviderRegistry(),
        assembler=_Assembler(),
        retrieval_provider=lambda: RETRIEVAL,
        publisher=publisher,
        probe_text=probe_text,
        client_factory=lambda _config, _spec: object(),
    )
    return config_service, activation, publisher


@pytest.mark.asyncio
async def test_activation_commits_then_publishes(repo):
    config_service, activation, publisher = _services(repo)
    config_service.create(_config())
    saved = await activation.activate("a", 1)
    assert saved.is_active is True
    assert repo.get_active_model().id == "a"
    assert publisher.calls == [(saved, AGENT, RETRIEVAL)]


@pytest.mark.asyncio
async def test_probe_failure_leaves_active_and_revision_untouched(repo):
    config_service, activation, publisher = _services(
        repo, probe_result=ChatProbeResult(streaming=False, tool_calling=False)
    )
    config_service.create(_config())
    with pytest.raises(ProtocolUnsupportedError):
        await activation.activate("a", 1)
    stored = repo.get_model("a")
    assert stored.is_active is False
    assert stored.revision == 1
    assert publisher.calls == []


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_before_publish(repo):
    config_service, activation, publisher = _services(repo)
    config_service.create(_config())
    with pytest.raises(RevisionConflictError):
        await activation.activate("a", 7)
    assert publisher.calls == []


@pytest.mark.asyncio
async def test_activation_can_save_full_config(repo):
    config_service, activation, publisher = _services(repo)
    config_service.create(_config())
    saved = await activation.activate("a", 1, _config(label="B"))
    assert saved.label == "B"
    assert saved.is_active is True
    assert publisher.calls[0][0].label == "B"
