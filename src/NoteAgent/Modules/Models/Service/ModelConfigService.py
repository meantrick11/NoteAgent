"""Model configuration use cases: CRUD, capability verification, pinned clients.

This service owns configuration rules and probes. It does not construct ChatAgents,
publish runtime snapshots, or touch embedding state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    CapabilityName,
    CapabilityRecord,
    disable_capability,
    find_capability,
    initial_capabilities,
    text_failed,
    text_ready,
    text_verified,
    vision_failed,
    vision_ready,
    vision_verified,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    InvalidProfileError,
    ModelConfigNotFoundError,
    ProtocolUnsupportedError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelRepository import ModelRepositoryPort
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderCatalogPort, ProviderSpec
from NoteAgent.Modules.Models.Provider.ModelClients import build_chat_model
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult, probe_model, probe_vision

_logger = logging.getLogger(__name__)

ProbeText = Callable[[BaseChatModel], Awaitable[ChatProbeResult]]
ProbeVision = Callable[[BaseChatModel], Awaitable[bool]]
BuildClient = Callable[[ModelConfig, ProviderSpec], BaseChatModel]


def _now() -> datetime:
    return datetime.now(UTC)


def _with_text(records: list[CapabilityRecord]) -> list[CapabilityRecord]:
    """Ensure a text row exists; new models always declare text."""
    return records if find_capability(records, "text") else [*initial_capabilities(), *records]


class ModelConfigService:
    """Configuration rules and capability evidence, independent of HTTP."""

    def __init__(
        self,
        *,
        repository: ModelRepositoryPort,
        catalog: ProviderCatalogPort,
        probe_text: ProbeText = probe_model,
        probe_vision: ProbeVision = probe_vision,
        client_factory: BuildClient = build_chat_model,
    ):
        self._repository = repository
        self._catalog = catalog
        self._probe_text = probe_text
        self._probe_vision = probe_vision
        self._client_factory = client_factory

    def list_models(self) -> list[ModelConfig]:
        return self._repository.list_models()

    def get_model(self, model_id: str) -> ModelConfig:
        model = self._repository.get_model(model_id)
        if model is None:
            raise ModelConfigNotFoundError(f"未找到模型配置 {model_id}")
        return model

    def get_active_model(self) -> ModelConfig | None:
        return self._repository.get_active_model()

    def create(self, config: ModelConfig) -> ModelConfig:
        """Persist a new, inactive configuration after provider validation."""
        spec = self._catalog.resolve(config.provider)
        config.validate_for(spec)
        prepared = config.model_copy(
            update={
                "id": config.id or uuid.uuid4().hex[:12],
                "is_active": False,
                "revision": 1,
                "capabilities": _with_text(config.capabilities),
            }
        )
        created = self._repository.create_model(prepared)
        _logger.info(
            "model config created id=%s provider=%s model=%s",
            created.id,
            created.provider,
            created.model,
        )
        return created

    def update(
        self, model_id: str, expected_revision: int, config: ModelConfig
    ) -> ModelConfig:
        """Update an inactive configuration; the repository resets evidence on changes."""
        spec = self._catalog.resolve(config.provider)
        config.validate_for(spec)
        updated = self._repository.update_model(
            model_id,
            expected_revision,
            config.model_copy(update={"capabilities": _with_text(config.capabilities)}),
        )
        _logger.info("model config updated id=%s revision=%s", updated.id, updated.revision)
        return updated

    def delete(self, model_id: str, expected_revision: int) -> None:
        self._repository.delete_model(model_id, expected_revision)
        _logger.info("model config deleted id=%s", model_id)

    async def test(self, config: ModelConfig) -> ChatProbeResult:
        """Probe a candidate without saving or activating it."""
        spec = self._catalog.resolve(config.provider)
        config.validate_for(spec)
        return await self._probe_text(self._client_factory(config, spec))

    async def verify_capability(
        self, model_id: str, capability: CapabilityName, expected_revision: int
    ) -> ModelConfig:
        """Probe and persist capability evidence using the row revision as CAS."""
        if capability not in ("text", "vision"):
            raise InvalidProfileError("仅支持 text 和 vision 能力验证")
        model = self.get_model(model_id)
        if model.revision != expected_revision:
            raise RevisionConflictError(
                f"配置已被其他操作更新（当前 revision={model.revision}），请刷新后重试"
            )
        spec = self._catalog.resolve(model.provider)
        client = self._client_factory(model, spec)
        text_result = await self._probe_text(client)
        records = self._record_text(model.capabilities, text_result)
        failure: str | None = None
        if capability == "vision":
            if not text_result.verified:
                records = self._record_vision_failure(records)
                failure = text_result.message or "模型未通过 text 验证，vision 未启用"
            else:
                passed = await self._probe_vision(client)
                if passed:
                    records = vision_verified(
                        records, evidence={"challenge": "2x6"}, checked_at=_now()
                    )
                else:
                    records = self._record_vision_failure(records)
                    failure = "模型未正确识别测试图片，vision 未启用"
        elif not text_result.verified:
            failure = text_result.message or "模型未通过验证"
        saved = self._repository.replace_capabilities(
            model_id, expected_revision, records
        )
        _logger.info(
            "capability verified id=%s capability=%s ok=%s revision=%s",
            model_id,
            capability,
            failure is None,
            saved.revision,
        )
        if failure is not None:
            raise ProtocolUnsupportedError(failure)
        return saved

    def disable_capability(
        self, model_id: str, capability: CapabilityName, expected_revision: int
    ) -> ModelConfig:
        """Pause text or vision; vision evidence is cleared so re-enabling reprobes."""
        if capability not in ("text", "vision"):
            raise InvalidProfileError("仅支持 text 和 vision 能力")
        model = self.get_model(model_id)
        records = disable_capability(model.capabilities, capability)
        saved = self._repository.replace_capabilities(
            model_id, expected_revision, records
        )
        _logger.info(
            "capability disabled id=%s capability=%s revision=%s",
            model_id,
            capability,
            saved.revision,
        )
        return saved

    def build_client_for_parse(
        self, model_id: str, expected_revision: int, *, vision: bool = True
    ) -> BaseChatModel:
        """Build a client for a source pinned to this model id and row revision."""
        model = self.get_model(model_id)
        if model.revision != expected_revision:
            raise RevisionConflictError("模型配置已变化，请重试解析")
        if not text_ready(model.capabilities):
            raise ProtocolUnsupportedError("该模型未通过 text 验证")
        if vision and not vision_ready(model.capabilities):
            raise ProtocolUnsupportedError("需要已验证 vision 的模型配置")
        spec = self._catalog.resolve(model.provider)
        return self._client_factory(model, spec)

    @staticmethod
    def _record_text(
        records: list[CapabilityRecord], result: ChatProbeResult
    ) -> list[CapabilityRecord]:
        evidence = {
            "streaming": result.streaming,
            "tool_calling": result.tool_calling,
        }
        if result.verified:
            return text_verified(records, evidence=evidence, checked_at=_now())
        return text_failed(records, evidence=evidence, checked_at=_now())

    @staticmethod
    def _record_vision_failure(
        records: list[CapabilityRecord],
    ) -> list[CapabilityRecord]:
        return vision_failed(
            records,
            evidence={"challenge": "failed"},
            checked_at=_now(),
        )
