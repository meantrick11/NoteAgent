"""聊天与本地向量模型切换的运行管理。

单一实例持有唯一的 RuntimeSnapshot：请求通过 read/write/chat 取一次快照并在整个操作内使用；
切换只在短发布锁内核对 revision、写盘、替换快照，任何失败都保留旧对象。

向量重建走串行维护窗口：期间拒绝新聊天与笔记写操作，读取与状态查询照常。装配入口由
bootstrap 注入（RuntimeAssembler），本模块不导入 bootstrap，避免循环依赖。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from langchain.tools import tool
from langchain_core.messages import HumanMessage
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
)
from pydantic import SecretStr, ValidationError

from noteagent.chat.agent import ChatAgent
from noteagent.model_management import catalog
from noteagent.model_management.schemas import (
    ActiveEmbedding,
    ChatActivateIn,
    ChatProfile,
    ChatProfileIn,
    ChatProfileOut,
    ChatProfileWriteIn,
    ChatTestOut,
    EmbeddingJobRecord,
    ModelSettingsStatusOut,
    StoredModelSettings,
)
from noteagent.model_management.store import (
    ModelSettingsRevisionError,
    ModelSettingsStore,
    default_chat_profile,
)
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.service import RetrievalService, index_targets

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from noteagent.bootstrap.settings import Settings

_logger = logging.getLogger(__name__)

# 每次连接测试最多两个短请求，单个请求的上限（秒）。没有隐藏重试。
PROBE_TIMEOUT_SECONDS = 20.0
# Chroma 对 collection 名长度有限制；base + 模型短名超长时截断。
COLLECTION_MAX_LENGTH = 63


class ModelManagementError(RuntimeError):
    """模型管理领域错误；HTTP 层按 status/code 映射成统一错误结构。"""

    status = 400
    code = "invalid_request"
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidProfileError(ModelManagementError):
    """The submitted profile cannot be used (missing key, unusable field, ...)."""

    status = 422
    code = "invalid_profile"


class RevisionConflictError(ModelManagementError):
    """The caller's expected_revision is stale."""

    status = 409
    code = "revision_conflict"
    retryable = True


class BusyError(ModelManagementError):
    """The app is inside a maintenance window, or an operation is in flight."""

    status = 409
    code = "busy"
    retryable = True


class ProfileNotFoundError(ModelManagementError):
    """Unknown chat profile id."""

    status = 404
    code = "profile_not_found"


class JobNotFoundError(ModelManagementError):
    """Unknown rebuild job id."""

    status = 404
    code = "job_not_found"


class ModelUnavailableError(ModelManagementError):
    """The requested embedding model is not usable locally."""

    status = 422
    code = "model_unavailable"


class UnknownModelError(ModelManagementError):
    """The requested embedding model id is not in the supported catalog."""

    status = 404
    code = "model_not_found"


class ModelProbeFailedError(ModelManagementError):
    """The chat service refused the request or could not be reached."""

    status = 502
    code = "probe_failed"
    retryable = True


class ModelProbeTimeoutError(ModelManagementError):
    """The chat service did not answer inside the probe timeout."""

    status = 504
    code = "probe_timeout"
    retryable = True


class ProtocolUnsupportedError(ModelManagementError):
    """The chat service answered but cannot serve this app's protocol needs."""

    status = 502
    code = "protocol_unsupported"


class RepairRequiredError(ModelManagementError):
    """The rebuild hit a condition the user has to resolve (external edit, ...)."""

    status = 409
    code = "repair_required"
    retryable = True


class RuntimeAssembler(Protocol):
    """Assembly entry injected by bootstrap, so this module never imports bootstrap."""

    def build_chat_model(self, profile: ChatProfile) -> BaseChatModel: ...

    def build_retrieval(
        self, *, model_id: str, collection: str, local_files_only: bool
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


@dataclass(frozen=True)
class ChatProbeResult:
    """What a connection test observed about one candidate."""

    streaming: bool
    tool_calling: bool
    message: str | None = None

    @property
    def verified(self) -> bool:
        """A candidate is only usable when both capabilities work."""
        return self.streaming and self.tool_calling


@tool("probe_tool", description="回显传入的 value，用于验证工具调用协议。")
def _probe_tool(value: str) -> str:
    """Echo the probe value back to the model."""
    return value


def embedding_collection_name(base: str, model_id: str) -> str:
    """Give each embedding model its own collection.

    Vectors from different models are not comparable, so a switch must never write into
    the collection the previous model built.
    """
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", model_id.rsplit("/", 1)[-1])
    return f"{base}__{slug}"[:COLLECTION_MAX_LENGTH]


def _now() -> datetime:
    """UTC timestamp for job records."""
    return datetime.now(UTC)


def _chunk_text(content: object) -> str:
    """Displayable text of a streamed chunk's content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


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


def _public_error(exc: Exception) -> str:
    """Collapse an exception into a message safe to show and to persist in job state.

    Provider errors may quote an endpoint or a header, so they are replaced by a
    category. Local errors keep their type plus a short message, which is what makes a
    failed rebuild diagnosable.
    """
    if isinstance(exc, ModelManagementError):
        return exc.message
    if isinstance(exc, APITimeoutError):
        return "模型服务响应超时"
    if isinstance(exc, AuthenticationError):
        return "模型服务认证失败，请检查 API Key"
    if isinstance(exc, APIConnectionError):
        return "无法连接模型服务，请检查 Base URL 与网络"
    if isinstance(exc, APIStatusError):
        return f"模型服务返回 HTTP {exc.status_code}"
    message = str(exc).strip().replace("\n", " ")
    return f"{type(exc).__name__}: {message[:200]}"


def _probe_error(exc: Exception) -> ModelManagementError:
    """Classify a probe failure into a public error carrying the right status code."""
    if isinstance(exc, ModelManagementError):
        return exc
    if isinstance(exc, APITimeoutError):
        return ModelProbeTimeoutError("模型服务响应超时（20 秒内没有回复）")
    if isinstance(exc, AuthenticationError):
        return ModelProbeFailedError("模型服务认证失败，请检查 API Key")
    if isinstance(exc, APIConnectionError):
        return ModelProbeFailedError("无法连接模型服务，请检查 Base URL 与网络")
    if isinstance(exc, APIStatusError):
        return ModelProbeFailedError(f"模型服务返回 HTTP {exc.status_code}")
    return ModelProbeFailedError(f"模型调用失败（{type(exc).__name__}）")


def _describe_probe(result: ChatProbeResult) -> str:
    """Explain which capability a candidate lacks."""
    missing: list[str] = []
    if not result.streaming:
        missing.append("流式输出")
    if not result.tool_calling:
        missing.append("工具调用")
    if not missing:
        return "模型未通过验证"
    return f"模型未通过验证：不支持 {'、'.join(missing)}，无法作为聊天模型使用"


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
    ):
        self._settings = settings
        self._store = store
        self._notes = notes
        self._assembler = assembler
        self._probe_impl = probe or self._default_probe
        # 一把状态锁：快照、计数、维护标志、配置文档都归它管；只覆盖同步短操作。
        self._lock = threading.Lock()
        self._active_operations = 0
        self._maintenance = False
        self._stopping = False
        self._document: StoredModelSettings | None = None
        self._snapshot: RuntimeSnapshot | None = None
        self._retrieval_problem: str | None = None
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
        retrieval, problem, embedding = self._open_retrieval(document)
        agent = self._assembler.build_agent(profile=profile, retrieval=retrieval)
        self._document = document
        self._retrieval_problem = problem
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
    def read(self) -> Iterator[RuntimeSnapshot]:
        """Read-only operation: allowed during maintenance, not counted."""
        yield self._current_snapshot()

    @contextmanager
    def write(self) -> Iterator[RuntimeSnapshot]:
        """Note-writing operation: refused during maintenance, counted."""
        snapshot = self._enter()
        try:
            yield snapshot
        finally:
            self._exit()

    @contextmanager
    def chat(self) -> Iterator[RuntimeSnapshot]:
        """One chat round: refused during maintenance, counted."""
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
            return ModelSettingsStatusOut(
                revision=document.revision,
                chat_profiles=[profile.to_out() for profile in document.chat_profiles],
                active_chat=active.to_out() if active else None,
                active_embedding=snapshot.embedding if snapshot else document.active_embedding,
                retrieval_available=snapshot is not None and snapshot.retrieval is not None,
                retrieval_problem=self._retrieval_problem,
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
        profile = self._merge_candidate(candidate, existing)
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
        """Create or update a stored profile. Saving never switches the runtime."""
        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(write.expected_revision)
            document = self._require_document()
            existing = document.profile_by_id(profile_id) if profile_id else None
            if profile_id and existing is None:
                raise ProfileNotFoundError(f"未找到配置 {profile_id}")
            if profile_id is not None and profile_id == document.active_chat_profile_id:
                # 直接改文件会让运行中的客户端与配置不一致，必须走"保存并启用"。
                raise BusyError("当前启用的配置不能直接编辑，请用「保存并启用」提交")
            profile = self._merge_candidate(write, existing, fallback_id=profile_id)
            profiles = [p for p in document.chat_profiles if p.id != profile.id]
            profiles.append(profile)
            # 只保存，不启用：启用必须走 activate_chat 的验证事务。
            self._save_locked(document.model_copy(update={"chat_profiles": profiles}))
            _logger.info("chat profile saved id=%s model=%s", profile.id, profile.model)
            return profile.to_out()

    async def activate_chat(self, payload: ChatActivateIn) -> ChatProfileOut:
        """Verify, save, and enable in one transaction; the old client stays on failure."""
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
                profile = self._merge_candidate(payload.profile, existing)
            else:
                profile = document.profile_by_id(payload.profile_id)
                if profile is None:
                    raise ProfileNotFoundError(f"未找到配置 {payload.profile_id}")
            retrieval = self._snapshot.retrieval if self._snapshot else None

        # 探针要发真实请求，不能持锁；结束到发布之间再核对一次 revision 与维护状态。
        result = await self._probe_impl(profile)
        if not result.verified:
            raise ProtocolUnsupportedError(_describe_probe(result))
        agent = self._assembler.build_agent(profile=profile, retrieval=retrieval)

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
            embedding = (
                self._snapshot.embedding if self._snapshot else saved.active_embedding
            )
            self._snapshot = RuntimeSnapshot(
                revision=saved.revision,
                chat_profile_id=profile.id,
                chat_label=profile.label,
                chat_agent=agent,
                retrieval=retrieval,
                embedding=embedding,
            )
        _logger.info(
            "chat profile activated id=%s model=%s provider=%s",
            profile.id,
            profile.model,
            profile.provider,
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

        Returns ``(unchanged, job)``: unchanged means the requested model is already in
        force with a matching fingerprint, so there is nothing to rebuild.
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

        with self._lock:
            self._ensure_not_maintenance()
            self._check_revision(expected_revision)
            if self._stopping:
                raise BusyError("服务正在关闭，不能启动重建")
            snapshot = self._snapshot
            active = snapshot.embedding if snapshot else None
            if (
                active is not None
                and active.model_id == candidate.model_id
                and snapshot is not None
                and snapshot.retrieval is not None
                and active.fingerprint == snapshot.retrieval.config_fingerprint()
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
            args=(candidate.model_id, candidate.resolved_revision, start_revision),
            name=f"embedding-rebuild-{job.id}",
            daemon=True,
        )
        self._job_thread = thread
        thread.start()
        _logger.info(
            "embedding rebuild started job=%s target=%s revision=%s",
            job.id,
            candidate.model_id,
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
    ) -> tuple[RetrievalService | None, str | None, ActiveEmbedding | None]:
        """Build retrieval for the persisted embedding state.

        Returns the service (or None), a user-facing reason when it is unavailable, and
        the embedding state with the fingerprint actually observed. A missing index is
        reported as unavailable rather than replaced by an empty one.
        """
        embedding = document.active_embedding
        if embedding is None:
            embedding = ActiveEmbedding(
                model_id=self._settings.embedding_model,
                collection=self._settings.chroma_collection,
            )
        try:
            retrieval = self._assembler.build_retrieval(
                model_id=embedding.model_id,
                collection=embedding.collection,
                local_files_only=self._settings.embedding_local_files_only,
            )
        except Exception as exc:
            _logger.exception(
                "启动时构建检索失败 model=%s collection=%s",
                embedding.model_id,
                embedding.collection,
            )
            return None, f"向量索引当前不可用：{_public_error(exc)}", embedding
        return retrieval, None, embedding.model_copy(
            update={"fingerprint": retrieval.config_fingerprint()}
        )

    def _merge_candidate(
        self,
        candidate: ChatProfileIn,
        existing: ChatProfile | None,
        *,
        fallback_id: str | None = None,
    ) -> ChatProfile:
        """Combine a submitted form with the stored profile it edits.

        An omitted key means "keep what is stored"; an explicit clear wins over
        everything. The mask shown in the UI is never accepted as a real key because the
        stored value is what we keep, not the submitted placeholder.
        """
        provided = candidate.provided_api_key()
        if candidate.clear_api_key:
            api_key, source = SecretStr(""), "ui"
        elif provided is not None:
            api_key, source = SecretStr(provided), "ui"
        elif existing is not None:
            api_key, source = existing.api_key, existing.credential_source
        else:
            api_key, source = SecretStr(""), "ui"

        if candidate.auth_mode == "api_key" and not api_key.get_secret_value().strip():
            raise InvalidProfileError("该配置要求 API Key，但当前没有可用凭据")

        if existing is not None:
            profile_id = existing.id
        elif candidate.id:
            profile_id = candidate.id
        elif fallback_id:
            profile_id = fallback_id
        else:
            profile_id = uuid.uuid4().hex[:12]

        try:
            return ChatProfile(
                id=profile_id,
                label=candidate.label,
                provider=candidate.provider,
                model=candidate.model,
                base_url=candidate.base_url,
                api_key=api_key,
                auth_mode=candidate.auth_mode,
                context_window=candidate.context_window,
                credential_source=source,
            )
        except ValidationError as exc:
            raise InvalidProfileError(f"配置内容不合法：{exc.error_count()} 处问题") from exc

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
        """Two short probe requests: real streaming, then real tool calling."""
        model = self._assembler.build_chat_model(profile)
        streaming = await self._probe_streaming(model)
        tool_calling = await self._probe_tool_calling(model)
        message = None if (streaming and tool_calling) else _describe_probe(
            ChatProbeResult(streaming=streaming, tool_calling=tool_calling)
        )
        return ChatProbeResult(
            streaming=streaming, tool_calling=tool_calling, message=message
        )

    async def _probe_streaming(self, model: BaseChatModel) -> bool:
        """Request 1/2: a short prompt must stream at least one text chunk."""
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                async for chunk in model.astream(
                    [HumanMessage(content="只回复两个字：你好")]
                ):
                    if _chunk_text(chunk.content):
                        return True
        except TimeoutError as exc:
            raise ModelProbeTimeoutError("模型服务响应超时（20 秒内没有回复）") from exc
        except Exception as exc:
            raise _probe_error(exc) from exc
        return False

    async def _probe_tool_calling(self, model: BaseChatModel) -> bool:
        """Request 2/2: a bound probe tool must actually be called."""
        bound = model.bind_tools([_probe_tool])
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                async for chunk in bound.astream(
                    [HumanMessage(content="请调用 probe_tool，value 传 ping。不要输出解释。")]
                ):
                    if getattr(chunk, "tool_calls", None) or getattr(
                        chunk, "tool_call_chunks", None
                    ):
                        return True
        except TimeoutError as exc:
            raise ModelProbeTimeoutError("工具调用验证超时（20 秒内没有回复）") from exc
        except Exception as exc:
            raise _probe_error(exc) from exc
        return False

    # ---------- 内部：重建 ----------

    def _rebuild_worker(
        self, model_id: str, resolved_revision: str | None, start_revision: int
    ) -> None:
        """Thread body: never let an exception escape, never leave the gate closed."""
        try:
            self._run_rebuild(model_id, resolved_revision, start_revision)
        except Exception as exc:
            _logger.exception("embedding rebuild failed target=%s", model_id)
            self._finish_job("failed", _public_error(exc))
        finally:
            with self._lock:
                self._maintenance = False
                self._job_thread = None

    def _run_rebuild(
        self, model_id: str, resolved_revision: str | None, start_revision: int
    ) -> None:
        """Build a fresh index for the target model, then publish it in one swap."""
        collection = embedding_collection_name(self._settings.chroma_collection, model_id)
        before = _note_manifest(self._notes)
        self._update_job(stage="loading")
        # 加载失败（缓存不完整等）直接抛错，旧索引与旧对象保持不变。
        retrieval = self._assembler.build_retrieval(
            model_id=model_id, collection=collection, local_files_only=True
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
        fingerprint = retrieval.config_fingerprint()
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
            self._live_job = None
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
