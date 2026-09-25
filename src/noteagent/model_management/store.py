"""模型选择配置的本地持久化。

只做三件事：读出/写入带版本号的 JSON、原子替换文件、维护 active 指针。这里不做 HTTP 调用，
也不装载任何模型，因此可以在单测里直接用临时目录跑。

凭据规则：环境（.env）提供的 Key 不复制进本文件，文件里只记 credential_source="env"，
加载时通过 :meth:`ModelSettingsStore.load_effective` 从 Settings 解析；用户在 UI 填写的 Key
才写入文件。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from noteagent.model_management.schemas import (
    ENV_PROFILE_ID,
    SCHEMA_VERSION,
    ActiveEmbedding,
    ChatProfile,
    StoredModelSettings,
)

if TYPE_CHECKING:
    from noteagent.bootstrap.settings import Settings

_logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"
# 凭据文件只保留给应用用户；Windows 上 chmod 基本不生效，属于尽力而为。
_OWNER_ONLY_MODE = 0o600


class ModelSettingsCorruptError(RuntimeError):
    """The settings file exists but cannot be parsed or validated.

    Raised instead of pretending the file is absent: silently rebuilding on top of a
    corrupt file would throw away the user's profiles and credentials.
    """


class ModelSettingsRevisionError(RuntimeError):
    """The caller's expected_revision no longer matches the stored revision."""


def default_chat_profile(settings: Settings) -> ChatProfile:
    """Build the fallback profile from environment configuration.

    The key is kept as a source reference (credential_source="env") so it stays in
    ``.env`` and is re-resolved from Settings on every load instead of being copied.
    """
    return ChatProfile(
        id=ENV_PROFILE_ID,
        label=f"环境默认（{settings.chat_model}）",
        provider="deepseek",
        model=settings.chat_model,
        base_url=settings.deepseek_api_base or "",
        api_key=settings.deepseek_api_key,
        auth_mode="api_key",
        context_window=settings.chat_context_window,
        credential_source="env",
    )


def initial_stored_settings(settings: Settings) -> StoredModelSettings:
    """Describe what an environment is running before any UI choice exists.

    The embedding state comes from Settings because that is what the current collection
    was actually built with; nothing here touches Chroma, so an existing index keeps the
    fingerprint it already has. ``fingerprint`` stays None until a runtime object exists
    and can report the real one.
    """
    profile = default_chat_profile(settings)
    return StoredModelSettings(
        schema_version=SCHEMA_VERSION,
        revision=0,
        chat_profiles=[profile],
        active_chat_profile_id=profile.id,
        active_embedding=ActiveEmbedding(
            model_id=settings.embedding_model,
            resolved_revision=None,
            collection=settings.chroma_collection,
            fingerprint=None,
        ),
    )


def _profile_to_file(profile: ChatProfile) -> dict[str, object]:
    """Serialize one profile for disk, keeping an env credential out of the file."""
    api_key = "" if profile.credential_source == "env" else profile.api_key.get_secret_value()
    return {
        "id": profile.id,
        "label": profile.label,
        "provider": profile.provider,
        "model": profile.model,
        "base_url": profile.base_url,
        "api_key": api_key,
        "auth_mode": profile.auth_mode,
        "context_window": profile.context_window,
        "credential_source": profile.credential_source,
    }


def _settings_to_file(settings: StoredModelSettings) -> dict[str, object]:
    """Serialize the whole document.

    Written by hand on purpose: ``model_dump`` would replace every SecretStr with
    ``**********``, and persisting that mask would destroy the stored credential.
    """
    embedding: dict[str, object] | None = None
    if settings.active_embedding is not None:
        embedding = settings.active_embedding.model_dump(mode="json")
    job: dict[str, object] | None = None
    if settings.embedding_job is not None:
        job = settings.embedding_job.model_dump(mode="json")
    return {
        "schema_version": settings.schema_version,
        "revision": settings.revision,
        "chat_profiles": [_profile_to_file(profile) for profile in settings.chat_profiles],
        "active_chat_profile_id": settings.active_chat_profile_id,
        "active_embedding": embedding,
        "embedding_job": job,
    }


class ModelSettingsStore:
    """Read and write ``<dir>/settings.json`` atomically."""

    def __init__(self, directory: Path):
        self._directory = directory
        self._path = directory / SETTINGS_FILE_NAME

    @property
    def path(self) -> Path:
        """Absolute path of the settings file, for diagnostics."""
        return self._path

    def load(self) -> StoredModelSettings | None:
        """Return the stored document as written, or None when never written.

        Env-sourced profiles come back with an empty key: use :meth:`load_effective`
        when the credentials need to be usable.
        """
        if not self._path.exists():
            return None
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ModelSettingsCorruptError(f"无法读取模型配置 {self._path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelSettingsCorruptError(
                f"模型配置 {self._path} 不是合法 JSON（第 {exc.lineno} 行）：{exc.msg}；"
                "请修复或备份后删除该文件再启动"
            ) from exc
        if not isinstance(data, dict):
            raise ModelSettingsCorruptError(f"模型配置 {self._path} 顶层必须是对象")
        self._check_schema_version(data)
        try:
            return StoredModelSettings.model_validate(data)
        except ValidationError as exc:
            raise ModelSettingsCorruptError(
                f"模型配置 {self._path} 结构不合法：{exc.error_count()} 处问题；"
                "请修复或备份后删除该文件再启动"
            ) from exc

    def _check_schema_version(self, data: dict) -> None:
        """Refuse a file written by a newer app instead of reinterpreting it.

        An older file (or one predating the version field) is accepted as-is: every
        field that ever existed has a default or is optional, so loading it keeps the
        stored profile ids, the active pointers, and any saved credential. Downgrading
        a newer file silently would drop whatever it added, so that is an error.
        """
        version = data.get("schema_version")
        if version is None:
            _logger.info("模型配置缺少 schema_version，按旧格式读取 path=%s", self._path)
            return
        if not isinstance(version, int) or version > SCHEMA_VERSION:
            raise ModelSettingsCorruptError(
                f"模型配置 {self._path} 的 schema_version={version!r} 高于本应用支持的 "
                f"{SCHEMA_VERSION}；请用写入该文件的版本打开，或备份后删除该文件再启动（原文件未改动）"
            )

    def load_effective(self, settings: Settings) -> StoredModelSettings:
        """Stored settings when present, otherwise an env-derived initial document.

        A persisted file always wins, including its active pointers. Before returning,
        env-sourced credentials are resolved from ``settings``. The fallback is returned
        without being written: starting the app must not create a config file as a side
        effect, so revision stays 0 until the user actually chooses something.
        """
        stored = self.load()
        if stored is None:
            return initial_stored_settings(settings)
        return self._resolve_env_credentials(stored, settings)

    def save(
        self,
        settings: StoredModelSettings,
        *,
        expected_revision: int | None = None,
    ) -> StoredModelSettings:
        """Atomically replace the file and bump the revision.

        ``expected_revision`` guards against a stale tab overwriting a newer choice.
        When the write itself fails the previous file is left untouched.
        """
        current = self.load()
        current_revision = current.revision if current is not None else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise ModelSettingsRevisionError(
                f"配置已被其他操作更新（磁盘 revision={current_revision}，"
                f"请求 revision={expected_revision}），请重新获取后再提交"
            )
        committed = settings.model_copy(update={"revision": current_revision + 1})
        self._write_atomic(committed)
        return committed

    def _resolve_env_credentials(
        self, settings: StoredModelSettings, app_settings: Settings
    ) -> StoredModelSettings:
        """Fill env-sourced credentials from .env, leaving UI-entered ones as stored.

        Only the DeepSeek default profile may reference the environment: the key in
        ``.env`` belongs to that vendor, so a profile that moved to another provider
        must carry its own credential (a UI one) instead of borrowing this key.
        """
        profiles: list[ChatProfile] = []
        for profile in settings.chat_profiles:
            if profile.credential_source == "env":
                if profile.provider == "deepseek":
                    profiles.append(
                        profile.model_copy(update={"api_key": app_settings.deepseek_api_key})
                    )
                    continue
                _logger.warning(
                    "配置引用了环境凭据但不适用 provider=%s profile=%s；该配置需要自己的 Key",
                    profile.provider,
                    profile.id,
                )
            profiles.append(profile)
        return settings.model_copy(update={"chat_profiles": profiles})

    def _write_atomic(self, settings: StoredModelSettings) -> None:
        """Write via a same-directory temp file so a failure cannot truncate the file."""
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _settings_to_file(settings), ensure_ascii=False, indent=2, sort_keys=True
        )
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._directory,
            prefix=f".{SETTINGS_FILE_NAME}.",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._restrict_to_owner(temp_path)
            os.replace(temp_path, self._path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            _logger.error("写入模型配置失败 path=%s error=%s", self._path, exc)
            raise
        _logger.info("模型配置已保存 path=%s revision=%s", self._path, settings.revision)

    @staticmethod
    def _restrict_to_owner(path: Path) -> None:
        """Best-effort owner-only permissions.

        POSIX honours 0o600; Windows only maps it onto the read-only bit, and some
        filesystems refuse chmod outright. Losing the restriction is acceptable and
        must never stop the app from saving its configuration, so this is non-fatal.
        """
        try:
            os.chmod(path, _OWNER_ONLY_MODE)
        except OSError as exc:
            _logger.debug("无法设置配置文件权限 path=%s error=%s", path, exc)
