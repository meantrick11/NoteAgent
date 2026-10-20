"""Vision parsing must use a pinned, verified model configuration."""

from types import SimpleNamespace

import pytest

from NoteAgent.AppBootstrap.SourceVision import vision_factory
from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    initial_capabilities,
    text_verified,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Sources.Parser.SourceFileParsers import ParseError

from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

CLIENT = object()


@pytest.fixture
def service():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = SqlModelConfigRepository(create_session_factory(engine))

    async def probe_text(_client):
        return ChatProbeResult(streaming=True, tool_calling=True)

    async def probe_vision(_client):
        return True

    configs = ModelConfigService(
        repository=repo,
        catalog=ProviderRegistry(),
        probe_text=probe_text,
        probe_vision=probe_vision,
        client_factory=lambda _config, _spec: CLIENT,
    )
    configs.create(
        ModelConfig(
            id="p",
            label="Model",
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret",
            capabilities=text_verified(
                initial_capabilities(),
                evidence={"streaming": True, "tool_calling": True},
                checked_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            ),
        )
    )
    return configs


def _source(media_type: str, revision: int = 1):
    return SimpleNamespace(
        media_type=media_type,
        parse_profile_id="p",
        parse_profile_revision=revision,
    )


def test_unverified_vision_cannot_parse_image(service):
    with pytest.raises(ParseError, match="已验证 vision"):
        vision_factory(_source("image/png"), service)


def test_unverified_vision_falls_back_for_pdf(service):
    assert vision_factory(_source("application/pdf"), service) is None


@pytest.mark.asyncio
async def test_verified_vision_returns_describer(service):
    await service.verify_capability("p", "vision", 1)
    describe = vision_factory(_source("image/png", revision=2), service)
    assert callable(describe)


def test_changed_revision_is_rejected(service):
    with pytest.raises(ParseError, match="已变化"):
        vision_factory(_source("image/png", revision=99), service)
