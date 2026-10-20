"""HTTP schemas for model configuration, providers, capabilities and status."""

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import CapabilityRecord
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig, normalize_base_url
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderSpec


class CapabilityOut(BaseModel):
    """Public capability row: no credential, only evidence metadata."""

    capability: str
    status: str
    verification: str
    source: str
    checked_at: datetime | None = None
    probe_version: int | None = None
    evidence: dict[str, object] | None = None


class ModelConfigOut(BaseModel):
    """One model configuration as returned by the HTTP API (never carries api_key)."""

    id: str
    label: str
    provider: str
    model: str
    base_url: str
    auth_mode: str
    has_api_key: bool
    timeout_s: int
    max_retries: int
    context_window: int
    temperature: float | None
    max_tokens: int | None
    is_active: bool
    revision: int
    capabilities: list[CapabilityOut]


class ProviderSpecOut(BaseModel):
    """Provider metadata used to render the settings form."""

    id: str
    label: str
    default_base_url: str
    base_url_required: bool
    auth_modes: list[str]


class ModelConfigIn(BaseModel):
    """Create or edit payload; an omitted key keeps the stored credential."""

    label: str
    provider: str
    model: str
    base_url: str = ""
    auth_mode: str = "api_key"
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    timeout_s: int = 60
    max_retries: int = 1
    context_window: int = 32768
    temperature: float | None = None
    max_tokens: int | None = None

    @field_validator("label", "model")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("配置名称与模型名不能为空")
        return candidate

    @field_validator("base_url")
    @classmethod
    def _base_url_valid(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("timeout_s", "context_window")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("数值必须是正整数")
        return value

    @field_validator("max_retries")
    @classmethod
    def _retries_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("重试次数不能为负数")
        return value

    @model_validator(mode="after")
    def _credential_intent(self) -> "ModelConfigIn":
        if self.clear_api_key and self.api_key is not None:
            raise ValueError("clear_api_key 与 api_key 不能同时提交")
        return self

    def provided_api_key(self) -> str | None:
        if self.api_key is None:
            return None
        value = self.api_key.get_secret_value().strip()
        return value or None


class ModelConfigWriteIn(ModelConfigIn):
    """Body for updating a stored configuration."""

    expected_revision: int


class ModelActivateIn(BaseModel):
    """Activate a stored model, optionally saving a full configuration first."""

    expected_revision: int
    config: ModelConfigIn | None = None


class CapabilityChangeIn(BaseModel):
    expected_revision: int


class ModelTestOut(BaseModel):
    verified: bool
    streaming: bool
    tool_calling: bool
    message: str | None = None


class ModelSettingsStatusOut(BaseModel):
    """Models plus retrieval state; each domain keeps its own revision."""

    models: list[ModelConfigOut]
    active_model: ModelConfigOut | None
    embedding_revision: int = 0
    active_embedding: dict[str, object] | None = None
    retrieval_available: bool
    retrieval_problem: str | None = None
    retrieval_state: str = "ok"
    indexed_files: int = 0
    corpus_files: int = 0
    busy: bool
    embedding_job: dict[str, object] | None = None


def to_capability_out(record: CapabilityRecord) -> CapabilityOut:
    return CapabilityOut(
        capability=record.capability,
        status=record.status,
        verification=record.verification,
        source=record.source,
        checked_at=record.checked_at,
        probe_version=record.probe_version,
        evidence=record.evidence,
    )


def to_model_out(model: ModelConfig) -> ModelConfigOut:
    return ModelConfigOut(
        id=model.id,
        label=model.label,
        provider=model.provider,
        model=model.model,
        base_url=model.base_url,
        auth_mode=model.auth_mode,
        has_api_key=model.has_api_key(),
        timeout_s=model.timeout_s,
        max_retries=model.max_retries,
        context_window=model.context_window,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        is_active=model.is_active,
        revision=model.revision,
        capabilities=[to_capability_out(item) for item in model.capabilities],
    )


def to_provider_out(spec: ProviderSpec) -> ProviderSpecOut:
    return ProviderSpecOut(
        id=spec.id,
        label=spec.label,
        default_base_url=spec.default_base_url,
        base_url_required=spec.base_url_required,
        auth_modes=list(spec.auth_modes),
    )


def merge_model_input(
    payload: ModelConfigIn,
    existing: ModelConfig | None,
    *,
    model_id: str,
) -> ModelConfig:
    """Combine a form payload with the stored credential and capabilities."""
    provided = payload.provided_api_key()
    if payload.clear_api_key:
        api_key = SecretStr("")
    elif provided is not None:
        api_key = SecretStr(provided)
    elif existing is not None:
        api_key = existing.api_key
    else:
        api_key = SecretStr("")
    capabilities = existing.capabilities if existing is not None else []
    return ModelConfig(
        id=model_id,
        label=payload.label,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        auth_mode=payload.auth_mode,
        api_key=api_key,
        timeout_s=payload.timeout_s,
        max_retries=payload.max_retries,
        context_window=payload.context_window,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        revision=existing.revision if existing is not None else 1,
        capabilities=capabilities,
    )
