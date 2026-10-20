"""Model configuration aggregate and validation rules.

The aggregate deliberately contains no storage or framework types. Provider-specific
rules are applied only when a :class:`ProviderSpec` is supplied by the catalog.
"""

from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator

from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import CapabilityRecord, initial_capabilities
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import InvalidProfileError
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import AuthMode, ProviderSpec

DEFAULT_CONTEXT_WINDOW = 32768
DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_RETRIES = 1


def normalize_base_url(value: str) -> str:
    """Validate a Base URL and strip a trailing slash.

    Only http/https are accepted, and embedded userinfo is rejected: a URL like
    ``https://user:pass@host`` would put a credential into the URL, which could then
    reach logs and error messages.
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


class ModelConfig(BaseModel):
    """One saved model configuration, including its connection fields and capabilities."""

    id: str
    label: str
    provider: str
    model: str
    base_url: str = ""
    auth_mode: AuthMode = "api_key"
    api_key: SecretStr = SecretStr("")
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    context_window: int = DEFAULT_CONTEXT_WINDOW
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool = False
    revision: int = 1
    capabilities: list[CapabilityRecord] = Field(default_factory=initial_capabilities)

    @field_validator("label", "model")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("配置名称与模型名不能为空")
        return candidate

    @field_validator("base_url")
    @classmethod
    def _base_url_valid(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("context_window")
    @classmethod
    def _context_window_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("上下文窗口必须是正整数")
        return value

    @field_validator("timeout_s")
    @classmethod
    def _timeout_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("超时时间必须是正整数")
        return value

    @field_validator("max_retries")
    @classmethod
    def _retries_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("重试次数不能为负数")
        return value

    def has_api_key(self) -> bool:
        """True when a credential is present; auth_mode=none needs none."""
        return bool(self.api_key.get_secret_value().strip())

    def effective_base_url(self, spec: ProviderSpec) -> str:
        """The Base URL the client should use, falling back to the provider default."""
        return self.base_url or spec.default_base_url

    def validate_for(self, spec: ProviderSpec) -> None:
        """Apply the rules declared by the provider catalog."""
        if self.provider != spec.id:
            raise InvalidProfileError(
                f"配置的 provider={self.provider!r} 与规格 {spec.id!r} 不一致"
            )
        if spec.base_url_required and not self.effective_base_url(spec):
            raise InvalidProfileError(f"Provider「{spec.label}」必须填写 Base URL")
        if self.auth_mode not in spec.auth_modes:
            raise InvalidProfileError(
                f"Provider「{spec.label}」不支持认证方式 {self.auth_mode}"
            )
        if self.auth_mode == "api_key" and not self.has_api_key():
            raise InvalidProfileError("该配置要求 API Key，但当前没有可用凭据")

    def same_connection(self, other: "ModelConfig") -> bool:
        """Whether provider identity and credential are unchanged.

        Any change here invalidates capability evidence.
        """
        return (
            self.provider == other.provider
            and self.model == other.model
            and self.base_url == other.base_url
            and self.auth_mode == other.auth_mode
            and self.api_key.get_secret_value() == other.api_key.get_secret_value()
        )
