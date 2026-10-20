"""One-time, idempotent import of the legacy model settings JSON."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    TEXT_PROBE_VERSION,
    VISION_PROBE_VERSION,
    CapabilityRecord,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import ChatProfile, StoredModelSettings
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import InvalidProfileError
from NoteAgent.Modules.Models.Domain.Vo.ModelRepository import ModelRepositoryPort
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderCatalogPort
from NoteAgent.Modules.Models.Mapper.LegacyModelSettingsReader import LegacyModelSettingsReader
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore

_logger = logging.getLogger(__name__)

LEGACY_BACKUP_NAME = "settings.pre-db.json"


@dataclass(frozen=True)
class ImportResult:
    """Outcome of the legacy import."""

    imported: int = 0
    skipped: bool = False
    archived: bool = False


class LegacyModelSettingsImporter:
    """Move chat profiles from the old JSON document into the database."""

    def __init__(
        self,
        *,
        repository: ModelRepositoryPort,
        catalog: ProviderCatalogPort,
        store: ModelSettingsStore,
        settings,
    ):
        self._repository = repository
        self._catalog = catalog
        self._store = store
        self._settings = settings
        self._reader = LegacyModelSettingsReader(store)

    def run(self) -> ImportResult:
        """Import when the table is empty; always scrub legacy chat profiles."""
        document = self._reader.read(self._settings)
        if document is None:
            return ImportResult(skipped=self._repository.count_models() > 0)
        if self._repository.count_models() > 0:
            archived = self._archive(document)
            return ImportResult(skipped=True, archived=archived)
        active_id = document.active_chat_profile_id
        if not any(profile.id == active_id for profile in document.chat_profiles):
            active_id = None
        models = [self._to_model(profile) for profile in document.chat_profiles]
        imported = self._repository.import_models(models, active_id)
        archived = self._archive(document) if imported else False
        _logger.info(
            "legacy model settings imported count=%s active=%s archived=%s",
            imported,
            active_id or "-",
            archived,
        )
        return ImportResult(imported=imported, archived=archived)

    def _to_model(self, profile: ChatProfile) -> ModelConfig:
        """Map one legacy profile into the new aggregate."""
        spec = self._catalog.resolve(profile.provider)
        config = ModelConfig(
            id=profile.id,
            label=profile.label,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            auth_mode=profile.auth_mode,
            api_key=profile.api_key,
            timeout_s=60,
            max_retries=1,
            context_window=profile.context_window,
            capabilities=self._capabilities(profile),
        )
        try:
            config.validate_for(spec)
        except InvalidProfileError as exc:
            raise InvalidProfileError(f"旧配置 {profile.id} 无法导入：{exc.message}") from exc
        return config

    @staticmethod
    def _capabilities(profile: ChatProfile) -> list[CapabilityRecord]:
        """Translate the old capability lists into structured records."""
        records: list[CapabilityRecord] = []
        text_verified = "text" in profile.verified_capabilities
        records.append(
            CapabilityRecord(
                capability="text",
                status="enabled" if profile.text_enabled else "disabled",
                verification="verified" if text_verified else "unverified",
                source="probe" if text_verified else "manual",
                checked_at=profile.capability_checked_at.get("text") if text_verified else None,
                probe_version=TEXT_PROBE_VERSION if text_verified else None,
            )
        )
        if "vision" in profile.capabilities:
            vision_verified = "vision" in profile.verified_capabilities
            records.append(
                CapabilityRecord(
                    capability="vision",
                    status="enabled",
                    verification="verified" if vision_verified else "unverified",
                    source="probe" if vision_verified else "manual",
                    checked_at=profile.capability_checked_at.get("vision") if vision_verified else None,
                    probe_version=VISION_PROBE_VERSION if vision_verified else None,
                )
            )
        return records

    def _archive(self, document: StoredModelSettings) -> bool:
        """Back up the legacy file and remove chat profiles from the live file."""
        if not document.chat_profiles:
            return False
        backup = self._store.path.with_name(LEGACY_BACKUP_NAME)
        if not backup.exists():
            shutil.copy2(self._store.path, backup)
            try:
                os.chmod(backup, 0o600)
            except OSError:
                _logger.debug("无法限制遗留备份权限 path=%s", backup)
        scrubbed = document.model_copy(
            update={"chat_profiles": [], "active_chat_profile_id": None}
        )
        self._store.save(scrubbed, expected_revision=document.revision)
        _logger.info("legacy model settings archived backup=%s", backup)
        return True
