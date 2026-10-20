"""Activation orchestration: probe, build, commit, publish.

The database transaction is the only place where the active pointer changes. Any
failure before it leaves the previous model, revision and snapshot untouched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import text_verified
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    InvalidProfileError,
    ProtocolUnsupportedError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelRepository import ModelRepositoryPort
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderCatalogPort, ProviderSpec
from NoteAgent.Modules.Models.Provider.ModelClients import build_chat_model
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult, probe_model
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Models.Service.ModelPorts import (
    AgentAssemblerPort,
    RetrievalProviderPort,
    RuntimePublisherPort,
)

_logger = logging.getLogger(__name__)

ProbeText = Callable[[BaseChatModel], Awaitable[ChatProbeResult]]
BuildClient = Callable[[ModelConfig, ProviderSpec], BaseChatModel]


def _now() -> datetime:
    return datetime.now(UTC)


class ModelActivationService:
    """Enable one model using the existing two-phase reliability semantics."""

    def __init__(
        self,
        *,
        repository: ModelRepositoryPort,
        config_service: ModelConfigService,
        catalog: ProviderCatalogPort,
        assembler: AgentAssemblerPort,
        retrieval_provider: RetrievalProviderPort,
        publisher: RuntimePublisherPort,
        probe_text: ProbeText = probe_model,
        client_factory: BuildClient = build_chat_model,
    ):
        self._repository = repository
        self._config_service = config_service
        self._catalog = catalog
        self._assembler = assembler
        self._retrieval_provider = retrieval_provider
        self._publisher = publisher
        self._probe_text = probe_text
        self._client_factory = client_factory

    async def activate(
        self,
        model_id: str,
        expected_revision: int,
        config: ModelConfig | None = None,
    ) -> ModelConfig:
        """Verify the candidate, build the agent, switch active, then publish."""
        candidate = config or self._config_service.get_model(model_id)
        if candidate.id != model_id:
            raise InvalidProfileError("请求体中的 id 与路径不一致")
        candidate = candidate.model_copy(update={"revision": expected_revision})
        spec = self._catalog.resolve(candidate.provider)
        candidate.validate_for(spec)
        client = self._client_factory(candidate, spec)
        result = await self._probe_text(client)
        if not result.verified:
            raise ProtocolUnsupportedError(result.message or "模型未通过验证")
        capabilities = text_verified(
            candidate.capabilities,
            evidence={
                "streaming": result.streaming,
                "tool_calling": result.tool_calling,
            },
            checked_at=_now(),
        )
        candidate = candidate.model_copy(update={"capabilities": capabilities})
        retrieval = self._retrieval_provider()
        agent = self._assembler.build_agent(model=candidate, retrieval=retrieval)
        saved = self._repository.activate_model(model_id, expected_revision, candidate)
        self._publisher.publish(model=saved, agent=agent, retrieval=retrieval)
        _logger.info(
            "model activated id=%s provider=%s model=%s revision=%s",
            saved.id,
            saved.provider,
            saved.model,
            saved.revision,
        )
        return saved
