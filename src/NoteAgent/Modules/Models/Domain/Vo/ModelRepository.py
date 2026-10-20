"""Storage port for model configurations.

All writes use a row-level revision. The adapter owns transactions; services never
see SQLAlchemy types or raw SQL.
"""

from typing import Protocol

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import CapabilityRecord
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig


class ModelRepositoryPort(Protocol):
    """Persistence operations required by model configuration use cases."""

    def list_models(self) -> list[ModelConfig]: ...

    def get_model(self, model_id: str) -> ModelConfig | None: ...

    def get_active_model(self) -> ModelConfig | None: ...

    def count_models(self) -> int: ...

    def create_model(self, config: ModelConfig) -> ModelConfig: ...

    def update_model(
        self, model_id: str, expected_revision: int, config: ModelConfig
    ) -> ModelConfig:
        """Update a non-active model, invalidating evidence on connection changes."""
        ...

    def replace_capabilities(
        self,
        model_id: str,
        expected_revision: int,
        capabilities: list[CapabilityRecord],
    ) -> ModelConfig: ...

    def activate_model(
        self, model_id: str, expected_revision: int, config: ModelConfig | None = None
    ) -> ModelConfig:
        """Atomically switch the active row, optionally saving a full config first."""
        ...

    def delete_model(self, model_id: str, expected_revision: int) -> None: ...

    def import_models(
        self, models: list[ModelConfig], active_model_id: str | None
    ) -> int:
        """Insert legacy rows only when the table is empty; returns inserted count."""
        ...
