"""Live model/retrieval snapshot, operation leases and embedding rebuilds.

Model configuration itself lives in PostgreSQL and is handled by ModelConfigService /
ModelActivationService. This service owns only the live snapshot and the embedding
maintenance window.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from NoteAgent.Modules.Chat.Agent.Graph.ChatAgent import ChatAgent
from NoteAgent.Modules.Models.Domain.Dto.ModelSettingsSchemas import (
    ModelSettingsStatusOut,
    to_model_out,
)
from NoteAgent.Modules.Models.Domain.Vo import ModelCatalog as catalog
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import text_ready
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import (
    ActiveEmbedding,
    EmbeddingJobRecord,
    StoredModelSettings,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    BusyError,
    InvalidProfileError,
    JobNotFoundError,
    ModelNotConfiguredError,
    ModelUnavailableError,
    RepairRequiredError,
    RevisionConflictError,
    RuntimeConfigurationError,
    UnknownModelError,
    _public_error,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelRepository import ModelRepositoryPort
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import (
    ModelSettingsRevisionError,
    ModelSettingsStore,
)
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from NoteAgent.Modules.Retrieval.Engine.VectorStore.ChromaVectorStore import (
    CollectionMissingError,
    IndexConfigMismatch,
)
from NoteAgent.Modules.Retrieval.Service.NoteRetrievalService import RetrievalService, index_targets

if TYPE_CHECKING:
    from NoteAgent.AppBootstrap.AppSettings import Settings

_logger = logging.getLogger(__name__)

COLLECTION_MAX_LENGTH = 63
COLLECTION_DIGEST_LENGTH = 16
COLLECTION_MODEL_SLUG_LENGTH = 24


class RuntimeAssembler(Protocol):
    """Assembly entry injected by bootstrap; no concrete imports in this module."""

    def build_agent(self, *, model: ModelConfig, retrieval: RetrievalService | None) -> ChatAgent: ...

    def index_fingerprint(self, *, model_id: str, resolved_revision: str | None) -> str: ...

    def build_retrieval(
        self,
        *,
        model_id: str,
        resolved_revision: str | None,
        collection: str,
        local_files_only: bool,
        create_if_missing: bool,
    ) -> RetrievalService: ...


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Every runtime object one request needs; fixed for the whole operation."""

    model: ModelConfig | None
    chat_agent: ChatAgent | None
    retrieval: RetrievalService | None
    embedding: ActiveEmbedding | None
    embedding_revision: int

    @property
    def revision(self) -> int:
        """Active model revision; zero when no model is configured."""
        return self.model.revision if self.model is not None else 0

    @property
    def chat_model_id(self) -> str | None:
        return self.model.id if self.model is not None else None

    def require_agent(self) -> ChatAgent:
        """The chat route only runs after a chat lease, so this must exist."""
        if self.chat_agent is None:
            raise ModelNotConfiguredError("尚未启用聊天模型，请先在设置中添加并启用模型")
        return self.chat_agent

    @property
    def embedding_model_id(self) -> str:
        return self.embedding.model_id if self.embedding else ""

    @property
    def collection(self) -> str:
        return self.embedding.collection if self.embedding else ""


def embedding_collection_name(base: str, model_id: str, fingerprint: str) -> str:
    """Name a collection after the full index identity, not just the model."""
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", model_id.rsplit("/", 1)[-1])[
        :COLLECTION_MODEL_SLUG_LENGTH
    ]
    suffix = f"{slug}-{fingerprint[:COLLECTION_DIGEST_LENGTH]}"
    prefix = base[: max(1, COLLECTION_MAX_LENGTH - len(suffix) - 2)]
    return f"{prefix}__{suffix}"


def _now() -> datetime:
    return datetime.now(UTC)


def _note_manifest(notes: FileNoteRepository) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for name in notes.list_notes():
        try:
            content = notes.read(name)
        except Exception:
            manifest[name] = "unreadable"
            continue
        manifest[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return manifest


def _first_query(notes: FileNoteRepository, file_name: str) -> str:
    try:
        content = notes.read(file_name)
    except Exception:
        return file_name
    for line in content.splitlines():
        stripped = line.lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return file_name


class ModelRuntimeService:
    """Owns the live snapshot, operation gate and embedding rebuild jobs."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: ModelRepositoryPort,
        store: ModelSettingsStore,
        notes: FileNoteRepository,
        assembler: RuntimeAssembler,
        workspace=None,
    ):
        self._settings = settings
        self._repository = repository
        self._store = store
        self._notes = notes
        self._assembler = assembler
        self._workspace = workspace
        self._lock = threading.Lock()
        self._active_operations = 0
        self._maintenance = False
        self._stopping = False
        self._embedding_document: StoredModelSettings | None = None
        self._snapshot: RuntimeSnapshot | None = None
        self._retrieval_problem: str | None = None
        self._retrieval_state: str = "ok"
        self._live_job: EmbeddingJobRecord | None = None
        self._job_thread: threading.Thread | None = None

    # ---------- startup / shutdown ----------

    def initialize(self) -> None:
        """Load the active model and embedding state, then build the snapshot."""
        document = self._store.load_effective(self._settings)
        job = document.embedding_job
        if job is not None and job.status == "running":
            document = document.model_copy(
                update={
                    "embedding_job": job.model_copy(
                        update={"status": "interrupted", "finished_at": _now()}
                    )
                }
            )
        retrieval, problem, embedding, retrieval_state = self._open_retrieval(document)
        model = self._repository.get_active_model()
        agent = None
        if model is not None:
            if not text_ready(model.capabilities):
                raise RuntimeConfigurationError(
                    f"当前启用的模型「{model.label}」({model.id}) 未通过 text 验证；"
                    "请在设置中重新验证或启用另一个模型"
                )
            try:
                agent = self._assembler.build_agent(model=model, retrieval=retrieval)
            except Exception as exc:
                _logger.error(
                    "启动失败：当前启用的模型不可用 id=%s provider=%s error=%s",
                    model.id,
                    model.provider,
                    exc,
                )
                raise RuntimeConfigurationError(
                    f"当前启用的模型「{model.label}」({model.id}) 无法使用：{exc}。"
                    "请在设置中修复该模型或启用另一个模型后重启"
                ) from exc
        self._embedding_document = document
        self._retrieval_problem = problem
        self._retrieval_state = retrieval_state
        self._snapshot = RuntimeSnapshot(
            model=model,
            chat_agent=agent,
            retrieval=retrieval,
            embedding=embedding,
            embedding_revision=document.revision,
        )
        _logger.info(
            "model runtime ready model=%s embedding=%s collection=%s retrieval=%s",
            model.id if model else "-",
            embedding.model_id if embedding else "-",
            embedding.collection if embedding else "-",
            "ok" if retrieval is not None else "unavailable",
        )

    def shutdown(self) -> None:
        with self._lock:
            self._stopping = True
        thread = self._job_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)

    # ---------- snapshot / leases ----------

    @contextmanager
    def read(self):
        with (self._workspace.operation("read") if self._workspace else nullcontext()):
            yield self._current_snapshot()

    @contextmanager
    def write(self):
        with (self._workspace.operation("mutate") if self._workspace else nullcontext()):
            snapshot = self._enter()
            try:
                yield snapshot
            finally:
                self._exit()

    @contextmanager
    def chat(self):
        with (self._workspace.operation("chat") if self._workspace else nullcontext()):
            snapshot = self._enter(require_chat=True)
            try:
                yield snapshot
            finally:
                self._exit()

    def snapshot(self) -> RuntimeSnapshot:
        return self._current_snapshot()

    def active_model(self) -> ModelConfig | None:
        return self._current_snapshot().model

    def publish(self, *, model: ModelConfig, agent: ChatAgent, retrieval: RetrievalService | None) -> None:
        """Publish a committed activation without touching embedding identity."""
        with self._lock:
            base = self._snapshot
            self._snapshot = RuntimeSnapshot(
                model=model,
                chat_agent=agent,
                retrieval=retrieval,
                embedding=base.embedding if base else None,
                embedding_revision=base.embedding_revision if base else 0,
            )

    def sync_model(self, model: ModelConfig) -> None:
        """Update an active model's capability state without rebuilding the agent."""
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None or snapshot.model is None:
                return
            if snapshot.model.id != model.id or not model.is_active:
                return
            self._snapshot = RuntimeSnapshot(
                model=model,
                chat_agent=snapshot.chat_agent,
                retrieval=snapshot.retrieval,
                embedding=snapshot.embedding,
                embedding_revision=snapshot.embedding_revision,
            )

    def status(self) -> ModelSettingsStatusOut:
        """Model list plus retrieval state; each domain keeps its own revision."""
        with self._lock:
            document = self._require_embedding_document()
            snapshot = self._snapshot
            active = snapshot.model if snapshot else None
            live_retrieval = snapshot.retrieval if snapshot else None
            problem = self._retrieval_problem
            state = self._retrieval_state
            indexed = 0
            if live_retrieval is not None:
                if not live_retrieval.verify_index():
                    state, problem = "missing", "索引 collection 已不存在，需要重建"
                    live_retrieval = None
                else:
                    indexed = live_retrieval.point_count()
                    state = "empty" if indexed == 0 else "ok"
            models = self._repository.list_models()
            if active is not None:
                models = [active if item.id == active.id else item for item in models]
            embedding = snapshot.embedding if snapshot else document.active_embedding
            job = self._live_job or document.embedding_job
            return ModelSettingsStatusOut(
                models=[to_model_out(item) for item in models],
                active_model=to_model_out(active) if active else None,
                embedding_revision=document.revision,
                active_embedding=embedding.model_dump(mode="json") if embedding else None,
                retrieval_available=live_retrieval is not None,
                retrieval_problem=problem,
                retrieval_state=state,
                indexed_files=indexed,
                corpus_files=self._corpus_file_count(),
                busy=self._maintenance,
                embedding_job=job.model_dump(mode="json") if job else None,
            )

    # ---------- embedding maintenance ----------

    def list_embedding_candidates(self) -> list[catalog.EmbeddingCandidate]:
        with self._lock:
            snapshot = self._snapshot
            active_id = snapshot.embedding_model_id if snapshot else None
        return catalog.list_candidates(
            self._settings.embedding_cache_dir, active_model_id=active_id
        )

    def switch_embedding(
        self, *, model_id: str, expected_revision: int
    ) -> tuple[bool, EmbeddingJobRecord | None]:
        try:
            candidate = catalog.inspect_model(
                self._settings.embedding_cache_dir,
                model_id,
                active_model_id=self._active_embedding_model_id(),
            )
        except catalog.UnknownEmbeddingModelError as exc:
            raise UnknownModelError(str(exc)) from exc
        if candidate.availability != "available":
            raise ModelUnavailableError(candidate.reason or "该向量模型当前不可用")
        target_fingerprint = self._assembler.index_fingerprint(
            model_id=candidate.model_id, resolved_revision=candidate.resolved_revision
        )
        collection = embedding_collection_name(
            self._settings.chroma_collection, candidate.model_id, target_fingerprint
        )
        with self._lock:
            self._ensure_not_maintenance()
            self._check_embedding_revision(expected_revision)
            if self._stopping:
                raise BusyError("服务正在关闭，不能启动重建")
            snapshot = self._snapshot
            active = snapshot.embedding if snapshot else None
            if (
                snapshot is not None
                and snapshot.retrieval is not None
                and active is not None
                and active.fingerprint == target_fingerprint
                and snapshot.retrieval.verify_index()
            ):
                return True, None
            if self._active_operations > 0:
                raise BusyError("有正在进行的聊天或写操作，请稍后再试")
            job = EmbeddingJobRecord(
                id=uuid.uuid4().hex[:12],
                status="running",
                stage="queued",
                active_model=active.model_id if active else "",
                target_model=candidate.model_id,
                started_at=_now(),
            )
            saved = self._save_embedding_locked(
                self._require_embedding_document().model_copy(
                    update={"embedding_job": job}
                )
            )
            start_revision = saved.revision
            self._live_job = job
            self._maintenance = True
        thread = threading.Thread(
            target=self._rebuild_worker,
            args=(
                candidate.model_id,
                candidate.resolved_revision,
                collection,
                target_fingerprint,
                start_revision,
            ),
            name=f"embedding-rebuild-{job.id}",
            daemon=True,
        )
        self._job_thread = thread
        thread.start()
        _logger.info(
            "embedding rebuild started job=%s target=%s collection=%s revision=%s",
            job.id,
            candidate.model_id,
            collection,
            start_revision,
        )
        return False, job

    def get_job(self, job_id: str) -> EmbeddingJobRecord:
        with self._lock:
            if self._live_job is not None and self._live_job.id == job_id:
                return self._live_job
            job = self._require_embedding_document().embedding_job
            if job is not None and job.id == job_id:
                return job
        raise JobNotFoundError(f"未找到重建任务 {job_id}")

    # ---------- internals ----------

    def _open_retrieval(
        self, document: StoredModelSettings
    ) -> tuple[RetrievalService | None, str | None, ActiveEmbedding | None, str]:
        embedding = document.active_embedding
        if embedding is None:
            embedding = ActiveEmbedding(
                model_id=self._settings.embedding_model,
                collection=self._settings.chroma_collection,
            )
        revision = self._resolve_revision(embedding)
        try:
            retrieval = self._assembler.build_retrieval(
                model_id=embedding.model_id,
                resolved_revision=revision,
                collection=embedding.collection,
                local_files_only=self._settings.embedding_local_files_only,
                create_if_missing=False,
            )
        except CollectionMissingError:
            _logger.error(
                "活动索引 collection 不存在 model=%s collection=%s",
                embedding.model_id,
                embedding.collection,
            )
            return (
                None,
                f"索引 collection「{embedding.collection}」不存在（可能已被删除或从未建立）；"
                "请重建索引后再使用检索",
                embedding,
                "missing",
            )
        except IndexConfigMismatch as exc:
            _logger.error("活动索引指纹不符 collection=%s error=%s", embedding.collection, exc)
            return (
                None,
                f"现有索引与当前配置不一致（{exc}）；请重建索引",
                embedding,
                "config_mismatch",
            )
        except Exception as exc:
            _logger.exception(
                "启动时构建检索失败 model=%s collection=%s",
                embedding.model_id,
                embedding.collection,
            )
            return None, f"向量索引当前不可用：{_public_error(exc)}", embedding, "unavailable"
        observed = embedding.model_copy(
            update={
                "resolved_revision": revision,
                "fingerprint": retrieval.config_fingerprint(),
            }
        )
        state = "empty" if retrieval.point_count() == 0 else "ok"
        return retrieval, None, observed, state

    def _resolve_revision(self, embedding: ActiveEmbedding) -> str | None:
        from_cache = catalog.resolved_revision(
            self._settings.embedding_cache_dir, embedding.model_id
        )
        return from_cache if from_cache is not None else embedding.resolved_revision

    def _corpus_file_count(self) -> int:
        targets, _skipped = index_targets(self._notes)
        return len(targets)

    def _save_embedding_locked(self, document: StoredModelSettings) -> StoredModelSettings:
        try:
            saved = self._store.save(document, expected_revision=document.revision)
        except ModelSettingsRevisionError as exc:
            raise RevisionConflictError(str(exc)) from exc
        self._embedding_document = saved
        return saved

    def _active_embedding_model_id(self) -> str | None:
        snapshot = self._snapshot
        if snapshot is None:
            return None
        return snapshot.embedding_model_id or None

    def _current_snapshot(self) -> RuntimeSnapshot:
        snapshot = self._snapshot
        if snapshot is None:
            raise BusyError("运行对象尚未就绪，请稍后重试")
        return snapshot

    def _enter(self, *, require_chat: bool = False) -> RuntimeSnapshot:
        with self._lock:
            if self._maintenance:
                raise BusyError("向量索引重建中：暂时不能发送消息或修改笔记，已有内容仍可查看")
            snapshot = self._snapshot
            if snapshot is None:
                raise BusyError("运行对象尚未就绪，请稍后重试")
            if require_chat:
                if snapshot.model is None or snapshot.chat_agent is None:
                    raise ModelNotConfiguredError(
                        "尚未启用聊天模型，请先在设置中添加并启用模型"
                    )
                if not text_ready(snapshot.model.capabilities):
                    raise InvalidProfileError("当前模型已关闭 text 能力，请先重新验证后再聊天")
            self._active_operations += 1
            return snapshot

    def _exit(self) -> None:
        with self._lock:
            if self._active_operations > 0:
                self._active_operations -= 1

    def _ensure_not_maintenance(self) -> None:
        if self._maintenance:
            raise BusyError("向量索引重建中：暂时不能修改模型配置")

    def _check_embedding_revision(self, expected_revision: int) -> None:
        current = self._embedding_document.revision if self._embedding_document else 0
        if expected_revision != current:
            raise RevisionConflictError(
                f"检索配置已被其他操作更新（当前 revision={current}），请重新获取后再提交"
            )

    def _require_embedding_document(self) -> StoredModelSettings:
        if self._embedding_document is None:
            raise BusyError("运行对象尚未就绪，请稍后重试")
        return self._embedding_document

    # ---------- rebuild ----------

    def _rebuild_worker(
        self,
        model_id: str,
        resolved_revision: str | None,
        collection: str,
        expected_fingerprint: str,
        start_revision: int,
    ) -> None:
        try:
            if self._workspace is None:
                self._run_rebuild(
                    model_id, resolved_revision, collection, expected_fingerprint, start_revision
                )
            else:
                with self._workspace.operation("model_rebuild"):
                    self._run_rebuild(
                        model_id, resolved_revision, collection, expected_fingerprint, start_revision
                    )
        except Exception as exc:
            _logger.exception("embedding rebuild failed target=%s", model_id)
            self._finish_job("failed", _public_error(exc))
        finally:
            with self._lock:
                self._release_rebuild_locked()

    def _release_rebuild_locked(self) -> None:
        if self._job_thread is threading.current_thread():
            self._maintenance = False
            self._job_thread = None

    def _run_rebuild(
        self,
        model_id: str,
        resolved_revision: str | None,
        collection: str,
        expected_fingerprint: str,
        start_revision: int,
    ) -> None:
        before = _note_manifest(self._notes)
        self._update_job(stage="loading")
        retrieval = self._assembler.build_retrieval(
            model_id=model_id,
            resolved_revision=resolved_revision,
            collection=collection,
            local_files_only=True,
            create_if_missing=True,
        )
        fingerprint = retrieval.config_fingerprint()
        if fingerprint != expected_fingerprint:
            raise RepairRequiredError(
                "目标索引的配置指纹与预期不符，已放弃本次重建（请重试或检查模型缓存）"
            )
        targets, _skipped = index_targets(self._notes)
        self._update_job(stage="indexing", total=len(targets), completed=0)
        chunks = 0
        for index, name in enumerate(targets, start=1):
            chunks += retrieval.index_note(name)
            self._update_job(completed=index)
        for stale in sorted(retrieval.indexed_files() - set(targets)):
            retrieval.delete_note(stale)
        after = _note_manifest(self._notes)
        if before != after:
            raise RepairRequiredError("重建期间笔记被外部修改，已保留旧索引，请重试")
        if targets and chunks == 0:
            raise RepairRequiredError("非空语料没有建立任何片段，候选索引不可用")
        if targets:
            self._update_job(stage="verifying")
            if not retrieval.search(_first_query(self._notes, targets[0]), top_k=1):
                raise RepairRequiredError("新索引检索不到已有语料，已保留旧索引")
        self._update_job(stage="publishing")

        with self._lock:
            if self._stopping:
                raise RepairRequiredError("服务正在关闭，已放弃本次重建（旧索引保持可用）")
            document = self._require_embedding_document()
            if document.revision != start_revision:
                raise RevisionConflictError("检索配置在重建期间被修改，已放弃本次重建")
            snapshot = self._snapshot
            model = snapshot.model if snapshot else None
            embedding = ActiveEmbedding(
                model_id=model_id,
                resolved_revision=resolved_revision,
                collection=collection,
                fingerprint=fingerprint,
            )
            job = self._require_live_job().model_copy(
                update={"status": "succeeded", "stage": "done", "finished_at": _now()}
            )
            agent = (
                self._assembler.build_agent(model=model, retrieval=retrieval)
                if model is not None
                else None
            )
            saved = self._save_embedding_locked(
                document.model_copy(
                    update={"active_embedding": embedding, "embedding_job": job}
                )
            )
            self._snapshot = RuntimeSnapshot(
                model=model,
                chat_agent=agent,
                retrieval=retrieval,
                embedding=embedding,
                embedding_revision=saved.revision,
            )
            self._retrieval_problem = None
            self._retrieval_state = "empty" if chunks == 0 else "ok"
            self._live_job = None
            self._release_rebuild_locked()
        _logger.info(
            "embedding rebuild published job=%s model=%s collection=%s chunks=%d notes=%d",
            job.id,
            model_id,
            collection,
            chunks,
            len(targets),
        )

    def _require_live_job(self) -> EmbeddingJobRecord:
        if self._live_job is None:
            raise RepairRequiredError("重建任务状态已丢失，已放弃发布")
        return self._live_job

    def _update_job(self, **fields) -> None:
        with self._lock:
            if self._live_job is None:
                return
            self._live_job = self._live_job.model_copy(update=fields)

    def _finish_job(self, status: str, error: str | None) -> None:
        with self._lock:
            live = self._live_job
            self._live_job = None
            if live is None:
                return
            record = live.model_copy(
                update={"status": status, "error": error, "finished_at": _now()}
            )
            try:
                document = self._require_embedding_document()
                self._save_embedding_locked(
                    document.model_copy(update={"embedding_job": record})
                )
            except Exception:
                _logger.exception("failed to persist embedding job failure id=%s", record.id)
