"""Read the legacy JSON settings document for one-time import.

Only the importer may touch this file once the database becomes authoritative.
"""

from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import StoredModelSettings
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore


class LegacyModelSettingsReader:
    """Thin read-only adapter around the legacy store."""

    def __init__(self, store: ModelSettingsStore):
        self._store = store

    @property
    def path(self):
        return self._store.path

    def read(self, settings) -> StoredModelSettings | None:
        """Return the effective legacy document, or None when no file exists."""
        if self._store.load() is None:
            return None
        return self._store.load_effective(settings)
