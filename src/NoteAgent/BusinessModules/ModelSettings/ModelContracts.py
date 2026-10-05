"""模型管理的请求、响应与内部存储结构。

内部结构（ChatProfile / StoredModelSettings）持有明文 Key，只能存在于服务端内存与本地
配置文件；对外的 ChatProfileOut 一律不含 api_key，只用 has_api_key 表达"有没有凭据"。
"""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, SecretStr, field_validator, model_validator

# 支持的 provider：项目已装 SDK 对应的协议，不做任意协议透传。
ChatProviderName = Literal["deepseek", "openai-compatible"]
AuthMode = Literal["api_key", "none"]
# 凭据来源：env 表示 Key 由环境提供、加载时从 Settings 解析；ui 表示用户填写并持久化。
CredentialSource = Literal["env", "ui"]
JobStatus = Literal["running", "succeeded", "failed", "interrupted"]
# 本地缓存里一个模型的可用程度：目录存在不等于 available。
EmbeddingAvailability = Literal["available", "incomplete", "unsupported"]
# 活动索引的真实状态，供界面区分"丢失""指纹不符""空但有效"和"已就绪"。
RetrievalState = Literal["ok", "empty", "missing", "config_mismatch", "unavailable"]

DEFAULT_CONTEXT_WINDOW = 32768
SCHEMA_VERSION = 1
# 从环境生成的默认 profile 使用固定 id，保证重启后 active 指针依然有效。
ENV_PROFILE_ID = "env-default"


def normalize_base_url(value: str) -> str:
    """Validate a Base URL and strip a trailing slash.

    Only http/https are accepted, and embedded userinfo is rejected: a URL like
    ``https://user:pass@host`` puts a credential into the URL, which would then reach
    logs and error messages.
    """
    candidate = value.strip()
    if not candidate:
        return ""
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    if not parts.netloc:
        raise ValueError("Base URL 缺少主机名")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Base URL 不能内嵌用户名或密码，凭据请填 API Key")
    return candidate.rstrip("/")


class ChatProfile(BaseModel):
    """One chat service configuration, including its plaintext credential.

    Never serialize this straight to a public response: use :meth:`to_out`.
    """

    id: str
    label: str
    provider: ChatProviderName
    model: str
    # 空 base_url 表示交给 SDK 自己的默认地址（目前只有 DeepSeek 允许）。
    base_url: str = ""
    api_key: SecretStr = SecretStr("")
    auth_mode: AuthMode = "api_key"
    context_window: int = DEFAULT_CONTEXT_WINDOW
    credential_source: CredentialSource = "ui"

    @field_validator("model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        """A profile without a model name can never issue a request."""
        candidate = value.strip()
        if not candidate:
            raise ValueError("模型名不能为空")
        return candidate

    @field_validator("base_url")
    @classmethod
    def _base_url_valid(cls, value: str) -> str:
        """Reject a malformed or credential-bearing URL before it is stored."""
        return normalize_base_url(value)

    @field_validator("context_window")
    @classmethod
    def _context_window_positive(cls, value: int) -> int:
        """The context window feeds ContextBudget, so zero or negative is meaningless."""
        if value <= 0:
            raise ValueError("上下文窗口必须是正整数")
        return value

    def has_api_key(self) -> bool:
        """True when a credential is present (auth_mode=none needs none)."""
        return bool(self.api_key.get_secret_value().strip())

    def to_out(self) -> "ChatProfileOut":
        """Public view: identical minus the secret, plus whether a key exists."""
        return ChatProfileOut(
            id=self.id,
            label=self.label,
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            auth_mode=self.auth_mode,
            context_window=self.context_window,
            has_api_key=self.has_api_key(),
            credential_source=self.credential_source,
        )


class ChatProfileOut(BaseModel):
    """One chat profile as returned by the HTTP API (never carries api_key)."""

    id: str
    label: str
    provider: ChatProviderName
    model: str
    base_url: str
    auth_mode: AuthMode
    context_window: int
    has_api_key: bool
    credential_source: CredentialSource


class ChatProfileIn(BaseModel):
    """Body for creating, editing, testing, or activating a chat profile.

    ``api_key`` stays a SecretStr so an accidental ``repr`` or log record masks it.
    An omitted key means "keep the stored one"; clearing requires ``clear_api_key``.
    """

    id: str | None = None
    label: str
    provider: ChatProviderName
    model: str
    base_url: str = ""
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    auth_mode: AuthMode = "api_key"
    context_window: int = DEFAULT_CONTEXT_WINDOW

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, value: str) -> str:
        """The label is what the input-box button shows, so it cannot be empty."""
        candidate = value.strip()
        if not candidate:
            raise ValueError("配置名称不能为空")
        return candidate

    @field_validator("model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        """A candidate without a model name can never be verified."""
        candidate = value.strip()
        if not candidate:
            raise ValueError("模型名不能为空")
        return candidate

    @field_validator("base_url")
    @classmethod
    def _base_url_valid(cls, value: str) -> str:
        """Reject a malformed or credential-bearing URL before any probe runs."""
        return normalize_base_url(value)

    @field_validator("context_window")
    @classmethod
    def _context_window_positive(cls, value: int) -> int:
        """The context window feeds ContextBudget, so zero or negative is meaningless."""
        if value <= 0:
            raise ValueError("上下文窗口必须是正整数")
        return value

    @model_validator(mode="after")
    def _check_provider_rules(self) -> "ChatProfileIn":
        """Enforce the per-provider rules the UI form relies on."""
        if self.provider != "deepseek" and not self.base_url:
            raise ValueError("OpenAI 兼容服务必须填写 Base URL")
        # DeepSeek 是官方托管服务，没有"无需认证"的部署形态。
        if self.provider == "deepseek" and self.auth_mode != "api_key":
            raise ValueError("DeepSeek 必须使用 API Key 认证")
        if self.clear_api_key and self.api_key is not None:
            raise ValueError("clear_api_key 与 api_key 不能同时提交")
        return self

    def provided_api_key(self) -> str | None:
        """The submitted key when it is usable, otherwise None.

        A blank submission counts as "not provided" so a form that posts an empty
        password box never overwrites a stored credential.
        """
        if self.api_key is None:
            return None
        value = self.api_key.get_secret_value().strip()
        return value or None


class ActiveEmbedding(BaseModel):
    """Which local embedding model currently backs the retrieval index.

    ``fingerprint`` is the collection config fingerprint actually in force. It is None
    only for the initial state recorded at first boot, before a runtime object exists.
    """

    model_id: str
    resolved_revision: str | None = None
    collection: str
    fingerprint: str | None = None


class EmbeddingJobRecord(BaseModel):
    """Progress and outcome of one vector rebuild.

    Kept public-safe on purpose: it is both persisted (so a restart can report an
    interrupted run) and returned by the API, so it must never hold a credential.
    """

    id: str
    status: JobStatus
    stage: str = "queued"
    completed: int = 0
    total: int = 0
    active_model: str
    target_model: str
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class StoredModelSettings(BaseModel):
    """The whole persisted model-settings document."""

    schema_version: int = SCHEMA_VERSION
    revision: int = 0
    chat_profiles: list[ChatProfile] = []
    active_chat_profile_id: str | None = None
    active_embedding: ActiveEmbedding | None = None
    embedding_job: EmbeddingJobRecord | None = None

    def active_chat_profile(self) -> ChatProfile | None:
        """The profile the runtime should be using, if the pointer resolves."""
        return self.profile_by_id(self.active_chat_profile_id)

    def profile_by_id(self, profile_id: str | None) -> ChatProfile | None:
        """Look up one stored profile by id."""
        if not profile_id:
            return None
        for profile in self.chat_profiles:
            if profile.id == profile_id:
                return profile
        return None


class ChatProfileWriteIn(ChatProfileIn):
    """Body for creating or updating a stored chat profile."""

    expected_revision: int


class ChatActivateIn(BaseModel):
    """Body for activating a chat profile: an existing id, or an inline candidate."""

    expected_revision: int
    profile_id: str | None = None
    profile: ChatProfileIn | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "ChatActivateIn":
        """Activating needs exactly one target, otherwise the intent is ambiguous."""
        if bool(self.profile_id) == bool(self.profile):
            raise ValueError("profile_id 与 profile 必须二选一")
        return self


class EmbeddingSwitchIn(BaseModel):
    """Body for switching the local embedding model."""

    model_id: str
    expected_revision: int


class ChatTestOut(BaseModel):
    """Outcome of a chat-profile connection test. Nothing is saved or switched."""

    verified: bool
    streaming: bool
    tool_calling: bool
    message: str | None = None


class EmbeddingCandidateOut(BaseModel):
    """One row of the embedding picker. Never carries a filesystem path."""

    model_id: str
    label: str
    availability: EmbeddingAvailability
    reason: str | None = None
    active: bool


class EmbeddingSwitchOut(BaseModel):
    """Result of asking for an embedding switch.

    ``unchanged`` means the requested model is already in force with a matching
    fingerprint, so no rebuild was started and ``job`` is null.
    """

    unchanged: bool
    job: EmbeddingJobRecord | None = None


class ModelSettingsStatusOut(BaseModel):
    """Everything the UI needs to render both pickers and any running job.

    ``retrieval_state`` is the machine-readable companion to ``retrieval_problem``:
    "empty" is a valid, available index (nothing to index yet), while "missing" and
    "config_mismatch" both mean the index has to be rebuilt before it can be trusted.
    """

    revision: int
    chat_profiles: list[ChatProfileOut]
    active_chat: ChatProfileOut | None
    active_embedding: ActiveEmbedding | None
    retrieval_available: bool
    retrieval_problem: str | None = None
    retrieval_state: RetrievalState = "ok"
    indexed_files: int = 0
    corpus_files: int = 0
    busy: bool
    embedding_job: EmbeddingJobRecord | None = None
