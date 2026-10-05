"""聊天与本地向量模型切换的运行管理。

单一实例持有唯一的 RuntimeSnapshot：请求通过 read/write/chat 取一次快照并在整个操作内使用；
切换只在短发布锁内核对 revision、写盘、替换快照，任何失败都保留旧对象。

向量重建走串行维护窗口：期间拒绝新聊天与笔记写操作，读取与状态查询照常。装配入口由
bootstrap 注入（RuntimeAssembler），本模块不导入 bootstrap，避免循环依赖。
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


from NoteAgent.BusinessModules.ChatAgent.ChatAgent import ChatAgent
from NoteAgent.BusinessModules.ModelSettings import ModelCatalog as catalog
from NoteAgent.BusinessModules.ModelSettings.ModelContracts import ActiveEmbedding, ChatActivateIn, ChatProfile, ChatProfileIn, ChatProfileOut, ChatProfileWriteIn, ChatTestOut, EmbeddingJobRecord, ModelSettingsStatusOut, StoredModelSettings
from NoteAgent.BusinessModules.ModelSettings.ModelSettingsStorage import ModelSettingsRevisionError, ModelSettingsStore, default_chat_profile
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteRetrieval.NoteRetrievalService import RetrievalService, index_targets
from NoteAgent.BusinessModules.NoteRetrieval.ChromaVectorStore import CollectionMissingError, IndexConfigMismatch

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from NoteAgent.AppBootstrap.AppSettings import Settings


from NoteAgent.BusinessModules.ModelSettings.ModelErrors import BusyError, InvalidProfileError, JobNotFoundError, ModelUnavailableError, ProfileNotFoundError, ProtocolUnsupportedError, RepairRequiredError, RevisionConflictError, RuntimeConfigurationError, UnknownModelError, _public_error
from NoteAgent.BusinessModules.ModelSettings.ModelProbes import ChatProbeResult, probe_model, _describe_probe
from NoteAgent.BusinessModules.ModelSettings.ModelProfiles import merge_candidate

_logger = logging.getLogger(__name__)

# 每次连接测试最多两个短请求，单个请求的上限（秒）。没有隐藏重试。

# Chroma 对 collection 名长度有限制；越过它的部分先裁前缀，指纹摘要永远保留完整。
COLLECTION_MAX_LENGTH = 63
COLLECTION_DIGEST_LENGTH = 16
COLLECTION_MODEL_SLUG_LENGTH = 24


class RuntimeAssembler(Protocol):
    """Assembly entry injected by bootstrap, so this module never imports bootstrap."""

    def build_chat_model(self, profile: ChatProfile) -> BaseChatModel: ...

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

    def build_agent(
        self, *, profile: ChatProfile, retrieval: RetrievalService | None
    ) -> ChatAgent: ...


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Every runtime object one request needs; fixed for the whole operation."""

    revision: int
    chat_profile_id: str
    chat_label: str
    chat_agent: ChatAgent
    retrieval: RetrievalService | None
    embedding: ActiveEmbedding | None

    @property
    def embedding_model_id(self) -> str:
        """Model id behind the current index; empty when no embedding state exists."""
        return self.embedding.model_id if self.embedding else ""

    @property
    def collection(self) -> str:
        """Collection currently backing retrieval; empty when unknown."""
        return self.embedding.collection if self.embedding else ""


def embedding_collection_name(base: str, model_id: str, fingerprint: str) -> str:
    """Name a collection after the *full* index identity, not just the model.

    The same embedding model under a different chunking strategy is a different index,
    so a model-only name would put two incompatible vector sets in one collection. The
    digest is what makes them distinct; the readable part is capped and the digest is
    never truncated, so two configurations can never truncate into the same name.
    """
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", model_id.rsplit("/", 1)[-1])[
        :COLLECTION_MODEL_SLUG_LENGTH
    ]
    suffix = f"{slug}-{fingerprint[:COLLECTION_DIGEST_LENGTH]}"
    prefix = base[: max(1, COLLECTION_MAX_LENGTH - len(suffix) - 2)]
    return f"{prefix}__{suffix}"


def _now() -> datetime:
    """UTC timestamp for job records."""
    return datetime.now(UTC)


def _note_manifest(notes: FileNoteRepository) -> dict[str, str]:
    """Relative path → content hash, to detect edits made outside the app."""
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
    """A short query drawn from a real note, for the post-rebuild smoke search."""
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
    """Owns the live runtime objects, the operation gate, and rebuild jobs."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: ModelSettingsStore,
        notes: FileNoteRepository,
        assembler: RuntimeAssembler,
        probe=None,
        workspace=None,
    ):
        self._settings = settings
        self._store = store
        self._notes = notes
        self._assembler = assembler
        self._probe_impl = probe or self._default_probe
        # 跨进程工作区门禁（可选）：重建期间独占，避免与恢复任务并行改正文／索引。
        self._workspace = workspace
        # 一把状态锁：快照、计数、维护标志、配置文档都归它管；只覆盖同步短操作。
        self._lock = threading.Lock()
        self._active_operations = 0
        self._maintenance = False
        self._stopping = False
        self._document: StoredModelSettings | None = None
        self._snapshot: RuntimeSnapshot | None = None
        self._retrieval_problem: str | None = None
        self._retrieval_state: str = "ok"
        self._live_job: EmbeddingJobRecord | None = None
        self._job_thread: threading.Thread | None = None

    # ---------- 启动与关闭 ----------

    def initialize(self) -> None:
        """Load persisted choices, build the runtime objects, and mark stale jobs.

        A broken index must not stop the app from starting: retrieval becomes explicitly
        unavailable instead, and the UI can rebuild it. Nothing is written to disk here,
        so booting never changes the configuration by itself.
        """
        document = self._store.load_effective(self._settings)
        job = document.embedding_job
        if job is not None and job.status == "running":
            # 重启后无法确认半成品索引的完整性：标为 interrupted，绝不自动启用。
            document = document.model_copy(
                update={
                    "embedding_job": job.model_copy(
                        update={"status": "interrupted", "finished_at": _now()}
                    )
                }
            )
        profile = document.active_chat_profile()
        if profile is None:
            # active 指针失效（文件被手工改过）时退回环境默认，避免整个应用不可用。
            profile = default_chat_profile(self._settings)
            document = document.model_copy(
                update={
                    "chat_profiles": [*document.chat_profiles, profile],
                    "active_chat_profile_id": profile.id,
                }
            )
        retrieval, problem, embedding, retrieval_state = self._open_retrieval(document)
        try:
            agent = self._assembler.build_agent(profile=profile, retrieval=retrieval)
        except Exception as exc:
            # 缺 Key 之类的问题必须说清"哪个配置、怎么修"，且绝不能悄悄换成另一个模型。
            _logger.error(
                "启动失败：当前启用的聊天配置不可用 profile=%s provider=%s error=%s",
                profile.id,
                profile.provider,
                exc,
            )
            raise RuntimeConfigurationError(
                f"当前启用的聊天配置「{profile.label}」({profile.id}) 无法使用：{exc}。"
                "请在「聊天模型」设置中为该配置填写 API Key（或改选其它配置）后重启"
            ) from exc
        self._document = document
        self._retrieval_problem = problem
        self._retrieval_state = retrieval_state
        self._snapshot = RuntimeSnapshot(
            revision=document.revision,
            chat_profile_id=profile.id,
            chat_label=profile.label,
            chat_agent=agent,
            retrieval=retrieval,
            embedding=embedding,
        )
        _logger.info(
            "model runtime ready chat=%s model=%s embedding=%s collection=%s retrieval=%s",
            profile.id,
            profile.model,
            embedding.model_id if embedding else "-",
            embedding.collection if embedding else "-",
            "ok" if retrieval is not None else "unavailable",
        )

    def shutdown(self) -> None:
        """Stop accepting new jobs and keep an in-flight job from publishing."""
        with self._lock:
            self._stopping = True
        thread = self._job_thread
        if thread is not None and thread.is_alive():
            # 不强行打断加载/索引；等它走到发布前的检查点自行放弃，最多 10 秒。
            thread.join(timeout=10.0)

    # ---------- 快照获取 ----------

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
            snapshot = self._enter()
            try:
                yield snapshot
            finally:
                self._exit()

    def snapshot(self) -> RuntimeSnapshot:
        """Current snapshot without joining the gate (for status rendering)."""
        return self._current_snapshot()

    def status(self) -> ModelSettingsStatusOut:
        """Everything the UI needs for both pickers and any running job."""
        with self._lock:
            document = self._require_document()
            active = document.active_chat_profile()
            snapshot = self._snapshot
            live_retrieval = snapshot.retrieval if snapshot else None
            problem = self._retrieval_problem
            state = self._retrieval_state
            indexed = 0
            if live_retrieval is not None:
                # 重建期间也要如实反映：索引被外部删掉时状态必须立刻变差。
                if not live_retrieval.verify_index():
                    state, problem = "missing", "索引 collection 已不存在，需要重建"
                    live_retrieval = None
                else:
                    indexed = live_retrieval.point_count()
                    state = "empty" if indexed == 0 else "ok"
            return ModelSettingsStatusOut(
                revision=document.revision,
                chat_profiles=[profile.to_out() for profile in document.chat_profiles],
                active_chat=active.to_out() if active else None,
                active_embedding=snapshot.embedding if snapshot else document.active_embedding,
                retrieval_available=live_retrieval is not None,
                retrieval_problem=problem,
                retrieval_state=state,
                indexed_files=indexed,
                corpus_files=self._corpus_file_count(),
                busy=self._maintenance,
                embedding_job=self._live_job or document.embedding_job,
            )

    # ---------- 聊天配置 ----------

    async def test_chat_profile(self, candidate: ChatProfileIn) -> ChatTestOut:
        """Probe a candidate without saving or switching anything."""
        with self._lock:
            existing = (
                self._require_document().profile_by_id(candidate.id) if candidate.id else None
            )
        # 测试不落盘，id 只用于把候选与它编辑的配置对齐（凭据保留规则依赖它）。
        probe_id = existing.id if existing is not None else (candidate.id or "probe")
        profile = merge_candidate(candidate, existing, profile_id=probe_id)
        result = await self._probe_impl(profile)
        return ChatTestOut(
            verified=result.verified,
            streaming=result.streaming,
            tool_calling=result.tool_calling,
            message=result.message,
        )

    def save_chat_profile(
        self, write: ChatProfileWriteIn, *, profile_id: str | None
    ) -> ChatProfileOut:
        """Create or update a stored profile. Saving never switches the runtime.

        ``profile_id`` is the identity: it comes from the URL on update and is None on
        create. A create always mints a server-side id, so a client-chosen id can never
        overwrite (or collide with) a stored profile; an update rejects a body id that
        contradicts the URL instead of quietly editing a different profile.
        """
        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(write.expected_revision)
            document = self._require_document()
            if profile_id is None:
                if write.id is not None:
                    _logger.info(
                        "忽略请求体中的 id=%s：新配置的 id 由服务端生成", write.id
                    )
                target_id = uuid.uuid4().hex[:12]
                existing = None
            else:
                if write.id is not None and write.id != profile_id:
                    raise InvalidProfileError(
                        f"请求体中的 id（{write.id}）与 URL 中的 profile_id（{profile_id}）不一致"
                    )
                existing = document.profile_by_id(profile_id)
                if existing is None:
                    raise ProfileNotFoundError(f"未找到配置 {profile_id}")
                if profile_id == document.active_chat_profile_id:
                    # 直接改文件会让运行中的客户端与配置不一致，必须走"保存并启用"。
                    raise BusyError("当前启用的配置不能直接编辑，请用「保存并启用」提交")
                target_id = profile_id
            profile = merge_candidate(write, existing, profile_id=target_id)
            profiles = [p for p in document.chat_profiles if p.id != profile.id]
            profiles.append(profile)
            # 只保存，不启用：启用必须走 activate_chat 的验证事务。
            self._save_locked(document.model_copy(update={"chat_profiles": profiles}))
            _logger.info("chat profile saved id=%s model=%s", profile.id, profile.model)
            return profile.to_out()

    def delete_chat_profile(self, *, profile_id: str, expected_revision: int) -> None:
        """Remove one stored profile. The active profile has to be switched away first.

        Only an explicit delete removes a profile (and with it its credential); editing
        or activating anything else must leave every other profile untouched.
        """
        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(expected_revision)
            document = self._require_document()
            profile = document.profile_by_id(profile_id)
            if profile is None:
                raise ProfileNotFoundError(f"未找到配置 {profile_id}")
            if profile_id == document.active_chat_profile_id:
                raise BusyError("当前启用的配置不能删除，请先启用另一个配置")
            profiles = [p for p in document.chat_profiles if p.id != profile_id]
            self._save_locked(document.model_copy(update={"chat_profiles": profiles}))
            _logger.info(
                "chat profile deleted id=%s provider=%s source=%s",
                profile.id,
                profile.provider,
                profile.credential_source,
            )

    async def activate_chat(self, payload: ChatActivateIn) -> ChatProfileOut:
        """Verify, save, and enable in one transaction; the old client stays on failure.

        Two phases on purpose: probing and building the new client happen outside the
        lock (they take seconds), then the commit re-checks revision, maintenance state,
        and the target profile inside the lock before persisting and publishing the new
        snapshot together. Any failure before the commit leaves the active pointer, the
        revision, the snapshot, and the running agent exactly as they were.
        """
        profile, retrieval = self._prepare_activation(payload)
        result = await self._probe_impl(profile)
        if not result.verified:
            raise ProtocolUnsupportedError(_describe_probe(result))
        agent = self._assembler.build_agent(profile=profile, retrieval=retrieval)
        return self._commit_activation(payload, profile, retrieval, agent)

    def _prepare_activation(
        self, payload: ChatActivateIn
    ) -> tuple[ChatProfile, RetrievalService | None]:
        """Resolve the target profile under the lock without changing anything."""
        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(payload.expected_revision)
            document = self._require_document()
            if payload.profile is not None:
                existing = (
                    document.profile_by_id(payload.profile.id) if payload.profile.id else None
                )
                if payload.profile.id and existing is None:
                    raise ProfileNotFoundError(f"未找到配置 {payload.profile.id}")
                target_id = existing.id if existing is not None else uuid.uuid4().hex[:12]
                profile = merge_candidate(payload.profile, existing, profile_id=target_id)
            else:
                profile = document.profile_by_id(payload.profile_id)
                if profile is None:
                    raise ProfileNotFoundError(f"未找到配置 {payload.profile_id}")
            retrieval = self._snapshot.retrieval if self._snapshot else None
            return profile, retrieval

    def _commit_activation(
        self,
        payload: ChatActivateIn,
        profile: ChatProfile,
        retrieval: RetrievalService | None,
        agent: ChatAgent,
    ) -> ChatProfileOut:
        """Persist the new profile and active pointer, then publish the snapshot."""
        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(payload.expected_revision)
            document = self._require_document()
            profiles = [p for p in document.chat_profiles if p.id != profile.id]
            profiles.append(profile)
            saved = self._save_locked(
                document.model_copy(
                    update={
                        "chat_profiles": profiles,
                        "active_chat_profile_id": profile.id,
                    }
                )
            )
            embedding = self._snapshot.embedding if self._snapshot else saved.active_embedding
            self._snapshot = RuntimeSnapshot(
                revision=saved.revision,
                chat_profile_id=profile.id,
                chat_label=profile.label,
                chat_agent=agent,
                retrieval=retrieval,
                embedding=embedding,
            )
        _logger.info(
            "chat profile activated id=%s model=%s provider=%s revision=%s",
            profile.id,
            profile.model,
            profile.provider,
            saved.revision,
        )
        return profile.to_out()

    def list_embedding_candidates(self) -> list[catalog.EmbeddingCandidate]:
        """Supported local embedding models plus the currently active one."""
        with self._lock:
            snapshot = self._snapshot
            active_id = snapshot.embedding_model_id if snapshot else None
        return catalog.list_candidates(
            self._settings.embedding_cache_dir, active_model_id=active_id
        )

    # ---------- 向量切换 ----------

    def switch_embedding(
        self, *, model_id: str, expected_revision: int
    ) -> tuple[bool, EmbeddingJobRecord | None]:
        """Open a maintenance window and start a rebuild.

        Returns ``(unchanged, job)``: unchanged means the running index already *has*
        the identity this request asks for and still exists, so there is nothing to
        rebuild. A collection that is missing, or whose identity differs (including a
        change to the chunking configuration), starts a repair job instead.
        """
        try:
            candidate = catalog.inspect_model(
                self._settings.embedding_cache_dir,
                model_id,
                active_model_id=self._active_model_id(),
            )
        except catalog.UnknownEmbeddingModelError as exc:
            raise UnknownModelError(str(exc)) from exc
        if candidate.availability != "available":
            raise ModelUnavailableError(candidate.reason or "该向量模型当前不可用")

        # 身份与目标 collection 必须在加载模型之前算出来：collection 名就是身份。
        target_fingerprint = self._assembler.index_fingerprint(
            model_id=candidate.model_id, resolved_revision=candidate.resolved_revision
        )
        collection = embedding_collection_name(
            self._settings.chroma_collection, candidate.model_id, target_fingerprint
        )

        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(expected_revision)
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
                # 检查与设置必须在同一把锁内，否则会漏掉刚进来的请求。
                raise BusyError("有正在进行的聊天或写操作，请稍后再试")
            job = EmbeddingJobRecord(
                id=uuid.uuid4().hex[:12],
                status="running",
                stage="queued",
                active_model=active.model_id if active else "",
                target_model=candidate.model_id,
                started_at=_now(),
            )
            saved = self._save_locked(
                self._require_document().model_copy(update={"embedding_job": job})
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
        """One rebuild job by id, live or persisted."""
        with self._lock:
            if self._live_job is not None and self._live_job.id == job_id:
                return self._live_job
            job = self._require_document().embedding_job
            if job is not None and job.id == job_id:
                return job
        raise JobNotFoundError(f"未找到重建任务 {job_id}")

    # ---------- 内部：装配与持久化 ----------

    def _open_retrieval(
        self, document: StoredModelSettings
    ) -> tuple[RetrievalService | None, str | None, ActiveEmbedding | None, str]:
        """Open the persisted index without ever creating or relabelling one.

        Returns the service (or None), a user-facing reason when it is unusable, the
        embedding state with the fingerprint actually observed, and the machine-readable
        state. A collection that is gone, or whose identity does not match the current
        configuration, is reported as such instead of being replaced by an empty one.
        """
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
        """Revision of the cached model as it exists right now.

        The revision is part of the index identity, so it must describe the weights on
        disk rather than whatever was recorded last time: an in-place model update then
        shows up as a fingerprint mismatch that requires a rebuild. A model the catalog
        does not know (a hand-placed cache) keeps its recorded revision instead.
        """
        from_cache = catalog.resolved_revision(
            self._settings.embedding_cache_dir, embedding.model_id
        )
        return from_cache if from_cache is not None else embedding.resolved_revision

    def _corpus_file_count(self) -> int:
        """How many notes the index is supposed to cover."""
        targets, _skipped = index_targets(self._notes)
        return len(targets)


    def _save_locked(self, document: StoredModelSettings) -> StoredModelSettings:
        """Persist while holding the state lock; a stale writer becomes a 409."""
        try:
            saved = self._store.save(document, expected_revision=document.revision)
        except ModelSettingsRevisionError as exc:
            raise RevisionConflictError(str(exc)) from exc
        self._document = saved
        return saved

    def _active_model_id(self) -> str | None:
        """Model id currently behind retrieval, if known."""
        snapshot = self._snapshot
        if snapshot is None:
            return None
        return snapshot.embedding_model_id or None

    def _current_snapshot(self) -> RuntimeSnapshot:
        """Snapshot for read-only use."""
        snapshot = self._snapshot
        if snapshot is None:
            raise BusyError("运行对象尚未就绪，请稍后重试")
        return snapshot

    def _enter(self) -> RuntimeSnapshot:
        """Take an operation lease unless a maintenance window is open."""
        with self._lock:
            if self._maintenance:
                raise BusyError(
                    "向量索引重建中：暂时不能发送消息或修改笔记，已有内容仍可查看"
                )
            snapshot = self._snapshot
            if snapshot is None:
                raise BusyError("运行对象尚未就绪，请稍后重试")
            self._active_operations += 1
            return snapshot

    def _exit(self) -> None:
        """Release an operation lease."""
        with self._lock:
            if self._active_operations > 0:
                self._active_operations -= 1

    def _ensure_not_maintenance(self) -> None:
        """Caller already holds the lock."""
        if self._maintenance:
            raise BusyError("向量索引重建中：暂时不能修改模型配置")

    def _check_revision(self, expected_revision: int) -> None:
        """Caller already holds the lock; a stale tab must not overwrite newer choices."""
        current = self._document.revision if self._document else 0
        if expected_revision != current:
            raise RevisionConflictError(
                f"配置已被其他操作更新（当前 revision={current}），请重新获取后再提交"
            )

    def _require_document(self) -> StoredModelSettings:
        """Caller already holds the lock."""
        if self._document is None:
            raise BusyError("运行对象尚未就绪，请稍后重试")
        return self._document

    # ---------- 内部：探针 ----------

    async def _default_probe(self, profile: ChatProfile) -> ChatProbeResult:
        """Probe a client supplied by the runtime assembler."""
        return await probe_model(self._assembler.build_chat_model(profile))


    # ---------- 内部：重建 ----------

    def _rebuild_worker(
        self,
        model_id: str,
        resolved_revision: str | None,
        collection: str,
        expected_fingerprint: str,
        start_revision: int,
    ) -> None:
        """Thread body: never let an exception escape, never leave the gate closed."""
        try:
            if self._workspace is None:
                self._run_rebuild(
                    model_id, resolved_revision, collection, expected_fingerprint, start_revision
                )
            else:
                # Exclusive: a recovery job can never run while an index rebuild does.
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
        """Only this worker can release its gate; a newer job may already own it."""
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
        """Build a fresh index for the target identity, then publish it in one swap.

        The new index is built in its own collection and only published after the whole
        corpus is indexed and verified; a failure anywhere leaves the old pointer, the
        old collection, and the old runtime objects untouched. Old collections are never
        deleted here — that is a separate, explicit cleanup step.
        """
        before = _note_manifest(self._notes)
        self._update_job(stage="loading")
        # 加载失败（缓存不完整等）直接抛错，旧索引与旧对象保持不变。
        retrieval = self._assembler.build_retrieval(
            model_id=model_id,
            resolved_revision=resolved_revision,
            collection=collection,
            local_files_only=True,
            create_if_missing=True,
        )
        fingerprint = retrieval.config_fingerprint()
        if fingerprint != expected_fingerprint:
            # 预计算与装配结果不一致：绝不把内容发布成另一个身份的索引。
            raise RepairRequiredError(
                "目标索引的配置指纹与预期不符，已放弃本次重建（请重试或检查模型缓存）"
            )
        targets, _skipped = index_targets(self._notes)
        self._update_job(stage="indexing", total=len(targets), completed=0)
        chunks = 0
        for index, name in enumerate(targets, start=1):
            chunks += retrieval.index_note(name)
            self._update_job(completed=index)
        # collection 里残留的、磁盘上已不存在的笔记要清掉，否则新索引会带着幽灵片段。
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
            document = self._require_document()
            if document.revision != start_revision:
                raise RevisionConflictError("配置在重建期间被修改，已放弃本次重建")
            profile = document.active_chat_profile()
            if profile is None:
                raise RepairRequiredError("当前聊天配置已失效，无法绑定新索引")
            embedding = ActiveEmbedding(
                model_id=model_id,
                resolved_revision=resolved_revision,
                collection=collection,
                fingerprint=fingerprint,
            )
            job = self._require_live_job().model_copy(
                update={"status": "succeeded", "stage": "done", "finished_at": _now()}
            )
            agent = self._assembler.build_agent(profile=profile, retrieval=retrieval)
            saved = self._save_locked(
                document.model_copy(
                    update={"active_embedding": embedding, "embedding_job": job}
                )
            )
            self._snapshot = RuntimeSnapshot(
                revision=saved.revision,
                chat_profile_id=profile.id,
                chat_label=profile.label,
                chat_agent=agent,
                retrieval=retrieval,
                embedding=embedding,
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
        """Caller already holds the lock."""
        if self._live_job is None:
            raise RepairRequiredError("重建任务状态已丢失，已放弃发布")
        return self._live_job

    def _update_job(self, **fields) -> None:
        """Refresh in-memory progress; disk is only written at start and at the end."""
        with self._lock:
            if self._live_job is None:
                return
            self._live_job = self._live_job.model_copy(update=fields)

    def _finish_job(self, status: str, error: str | None) -> None:
        """Record a failed outcome; the previous index and objects stay in force."""
        with self._lock:
            live = self._live_job
            self._live_job = None
            if live is None:
                return
            record = live.model_copy(
                update={"status": status, "error": error, "finished_at": _now()}
            )
            document = self._document
            if document is None:
                return
            try:
                self._save_locked(document.model_copy(update={"embedding_job": record}))
            except Exception:
                _logger.exception("记录重建结果失败 job=%s", record.id)
            finally:
                self._release_rebuild_locked()
