"""SQLAlchemy implementation of the model configuration repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from NoteAgent.Modules.Models.Domain.Po.ModelConfigModels import (
    ModelCapabilityRow,
    ModelConfigRow,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    CapabilityRecord,
    invalidate_capabilities,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    ActiveModelProtectedError,
    InvalidProfileError,
    ModelConfigNotFoundError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Mapper.ModelConfigMappers import (
    apply_config,
    to_domain,
    to_row,
)


def _has_text(records: list[CapabilityRecord]) -> bool:
    """Every model must keep a text capability row."""
    return any(record.capability == "text" for record in records)


def _connection_changed(row: ModelConfigRow, config: ModelConfig) -> bool:
    """Whether provider identity or credential differs from the stored row."""
    return (
        row.provider != config.provider
        or row.model != config.model
        or row.base_url != config.base_url
        or row.auth_mode != config.auth_mode
        or row.api_key != config.api_key.get_secret_value()
    )


def _sync_capabilities(
    session: Session, row: ModelConfigRow, records: list[CapabilityRecord]
) -> None:
    """Update capability rows in place to avoid delete/insert PK races."""
    existing = {item.capability: item for item in row.capabilities}
    wanted = {record.capability: record for record in records}
    for capability, record in wanted.items():
        target = existing.get(capability)
        if target is None:
            row.capabilities.append(
                ModelCapabilityRow(
                    model_id=row.id,
                    capability=record.capability,
                    status=record.status,
                    verification=record.verification,
                    source=record.source,
                    checked_at=record.checked_at,
                    probe_version=record.probe_version,
                    evidence=record.evidence,
                )
            )
            continue
        target.status = record.status
        target.verification = record.verification
        target.source = record.source
        target.checked_at = record.checked_at
        target.probe_version = record.probe_version
        target.evidence = record.evidence
    for capability, target in existing.items():
        if capability not in wanted:
            session.delete(target)


class SqlModelConfigRepository:
    """Row-level CAS repository backed by PostgreSQL or SQLite in tests."""

    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def list_models(self) -> list[ModelConfig]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ModelConfigRow).order_by(ModelConfigRow.created_at, ModelConfigRow.id)
            ).all()
            return [to_domain(row) for row in rows]

    def get_model(self, model_id: str) -> ModelConfig | None:
        with self._sessions() as session:
            row = session.get(ModelConfigRow, model_id)
            return to_domain(row) if row is not None else None

    def get_active_model(self) -> ModelConfig | None:
        with self._sessions() as session:
            row = session.scalars(
                select(ModelConfigRow).where(ModelConfigRow.is_active.is_(True))
            ).one_or_none()
            return to_domain(row) if row is not None else None

    def count_models(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count()).select_from(ModelConfigRow)) or 0)

    def create_model(self, config: ModelConfig) -> ModelConfig:
        if config.is_active:
            raise InvalidProfileError("新建配置不能直接启用，请使用激活流程")
        if not _has_text(config.capabilities):
            raise InvalidProfileError("模型配置必须包含 text 能力")
        row = to_row(config)
        row.revision = 1
        try:
            with self._sessions.begin() as session:
                session.add(row)
                session.flush()
                return to_domain(row)
        except IntegrityError as exc:
            raise InvalidProfileError("模型配置 id 已存在") from exc

    def update_model(
        self, model_id: str, expected_revision: int, config: ModelConfig
    ) -> ModelConfig:
        if model_id != config.id:
            raise InvalidProfileError("请求体中的 id 与路径不一致")
        with self._sessions.begin() as session:
            row = session.get(ModelConfigRow, model_id, with_for_update=True)
            if row is None:
                raise ModelConfigNotFoundError(f"未找到模型配置 {model_id}")
            if row.is_active:
                raise ActiveModelProtectedError(
                    "当前启用的模型不能直接编辑，请使用「保存并启用」"
                )
            self._check_revision(row, expected_revision)
            records = config.capabilities
            if _connection_changed(row, config):
                records = invalidate_capabilities(records)
            if not _has_text(records):
                raise InvalidProfileError("模型配置必须包含 text 能力")
            apply_config(row, config)
            _sync_capabilities(session, row, records)
            row.revision += 1
            session.flush()
            return to_domain(row)

    def replace_capabilities(
        self,
        model_id: str,
        expected_revision: int,
        capabilities: list[CapabilityRecord],
    ) -> ModelConfig:
        if not _has_text(capabilities):
            raise InvalidProfileError("模型配置必须包含 text 能力")
        with self._sessions.begin() as session:
            row = session.get(ModelConfigRow, model_id, with_for_update=True)
            if row is None:
                raise ModelConfigNotFoundError(f"未找到模型配置 {model_id}")
            self._check_revision(row, expected_revision)
            _sync_capabilities(session, row, capabilities)
            row.revision += 1
            session.flush()
            return to_domain(row)

    def activate_model(
        self, model_id: str, expected_revision: int, config: ModelConfig | None = None
    ) -> ModelConfig:
        with self._sessions.begin() as session:
            active_rows = session.scalars(
                select(ModelConfigRow)
                .where(ModelConfigRow.is_active.is_(True))
                .with_for_update()
            ).all()
            target = session.get(ModelConfigRow, model_id, with_for_update=True)
            if target is None:
                raise ModelConfigNotFoundError(f"未找到模型配置 {model_id}")
            self._check_revision(target, expected_revision)
            if config is not None:
                if config.id != model_id:
                    raise InvalidProfileError("请求体中的 id 与路径不一致")
                if not _has_text(config.capabilities):
                    raise InvalidProfileError("模型配置必须包含 text 能力")
                apply_config(target, config)
                _sync_capabilities(session, target, config.capabilities)
            for row in active_rows:
                if row.id != target.id:
                    row.is_active = False
            # Flush the old active flag before setting the new one so the partial
            # unique index never sees two active rows.
            session.flush()
            target.is_active = True
            target.revision += 1
            session.flush()
            return to_domain(target)

    def delete_model(self, model_id: str, expected_revision: int) -> None:
        with self._sessions.begin() as session:
            row = session.get(ModelConfigRow, model_id, with_for_update=True)
            if row is None:
                raise ModelConfigNotFoundError(f"未找到模型配置 {model_id}")
            if row.is_active:
                raise ActiveModelProtectedError("当前启用的模型不能删除，请先启用另一个模型")
            self._check_revision(row, expected_revision)
            session.delete(row)

    def import_models(
        self, models: list[ModelConfig], active_model_id: str | None
    ) -> int:
        if not models:
            return 0
        ids = {config.id for config in models}
        if len(ids) != len(models):
            raise InvalidProfileError("导入的模型 id 不得重复")
        if active_model_id is not None and active_model_id not in ids:
            raise InvalidProfileError("导入的 active 模型不在配置列表中")
        for config in models:
            if not _has_text(config.capabilities):
                raise InvalidProfileError(f"模型 {config.id} 缺少 text 能力")
        with self._sessions.begin() as session:
            if session.scalar(select(func.count()).select_from(ModelConfigRow)):
                return 0
            rows: list[ModelConfigRow] = []
            for config in models:
                row = to_row(config)
                row.revision = 1
                row.is_active = config.id == active_model_id
                rows.append(row)
            session.add_all(rows)
            session.flush()
            return len(rows)

    @staticmethod
    def _check_revision(row: ModelConfigRow, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise RevisionConflictError(
                f"配置已被其他操作更新（当前 revision={row.revision}，"
                f"请求 revision={expected_revision}），请刷新后重试"
            )
