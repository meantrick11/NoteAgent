"""Conversions between ORM rows and domain model objects."""

from pydantic import SecretStr

from NoteAgent.Modules.Models.Domain.Po.ModelConfigModels import (
    ModelCapabilityRow,
    ModelConfigRow,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import CapabilityRecord
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig


def to_capability_record(row: ModelCapabilityRow) -> CapabilityRecord:
    """Map one ORM capability row to its domain record."""
    return CapabilityRecord(
        capability=row.capability,
        status=row.status,
        verification=row.verification,
        source=row.source,
        checked_at=row.checked_at,
        probe_version=row.probe_version,
        evidence=row.evidence,
    )


def to_capability_rows(model_id: str, records: list[CapabilityRecord]) -> list[ModelCapabilityRow]:
    """Build fresh ORM capability rows for one model."""
    return [
        ModelCapabilityRow(
            model_id=model_id,
            capability=record.capability,
            status=record.status,
            verification=record.verification,
            source=record.source,
            checked_at=record.checked_at,
            probe_version=record.probe_version,
            evidence=record.evidence,
        )
        for record in records
    ]


def to_domain(row: ModelConfigRow) -> ModelConfig:
    """Map one ORM model row (with loaded capabilities) to the domain aggregate."""
    return ModelConfig(
        id=row.id,
        label=row.label,
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        auth_mode=row.auth_mode,
        api_key=SecretStr(row.api_key),
        timeout_s=row.timeout_s,
        max_retries=row.max_retries,
        context_window=row.context_window,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        is_active=row.is_active,
        revision=row.revision,
        capabilities=[to_capability_record(item) for item in row.capabilities],
    )


def to_row(config: ModelConfig) -> ModelConfigRow:
    """Create a new ORM row from a domain configuration."""
    return ModelConfigRow(
        id=config.id,
        label=config.label,
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        auth_mode=config.auth_mode,
        api_key=config.api_key.get_secret_value(),
        timeout_s=config.timeout_s,
        max_retries=config.max_retries,
        context_window=config.context_window,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        is_active=config.is_active,
        revision=config.revision,
        capabilities=to_capability_rows(config.id, config.capabilities),
    )


def apply_config(row: ModelConfigRow, config: ModelConfig) -> None:
    """Copy editable scalar fields from the domain object onto an existing row."""
    row.label = config.label
    row.provider = config.provider
    row.model = config.model
    row.base_url = config.base_url
    row.auth_mode = config.auth_mode
    row.api_key = config.api_key.get_secret_value()
    row.timeout_s = config.timeout_s
    row.max_retries = config.max_retries
    row.context_window = config.context_window
    row.temperature = config.temperature
    row.max_tokens = config.max_tokens
