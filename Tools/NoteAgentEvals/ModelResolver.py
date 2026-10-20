"""Resolve the active model from PostgreSQL for offline scripts and evals.

Scripts no longer read model names or credentials from ``.env``. They use the same
active model configuration as the running application, and may override only the
upstream model name for an independent Judge.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Common.Database import create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ModelClients import build_chat_model
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry


@dataclass(frozen=True)
class ResolvedModel:
    """One resolved model configuration plus its client."""

    config: ModelConfig
    client: BaseChatModel


def resolve_active_model(settings: Settings) -> ModelConfig:
    """Load the active model row, failing with an actionable message when absent."""
    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL is required to resolve the active model")
    engine = create_engine_from_url(settings.database_url)
    try:
        repository = SqlModelConfigRepository(create_session_factory(engine))
        model = repository.get_active_model()
    finally:
        engine.dispose()
    if model is None:
        raise RuntimeError(
            "没有启用的模型：请先在 Settings → 模型与连接 中添加并启用一个模型"
        )
    return model


def build_active_chat(settings: Settings) -> ResolvedModel:
    """Build the client for the active model."""
    model = resolve_active_model(settings)
    catalog = ProviderRegistry()
    spec = catalog.resolve(model.provider)
    model.validate_for(spec)
    return ResolvedModel(config=model, client=build_chat_model(model, spec))


def build_judge(settings: Settings, model_name: str | None = None) -> ResolvedModel:
    """Build a Judge on the active connection, optionally with another model name."""
    active = resolve_active_model(settings)
    effective_name = (model_name or active.model).strip()
    if not effective_name:
        raise RuntimeError("Judge model name is empty")
    config = active.model_copy(update={"model": effective_name})
    catalog = ProviderRegistry()
    spec = catalog.resolve(config.provider)
    config.validate_for(spec)
    return ResolvedModel(config=config, client=build_chat_model(config, spec))
