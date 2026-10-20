import logging

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import InvalidProfileError
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderSpec

_logger = logging.getLogger(__name__)

# 用户显式选择“无需认证”时给 SDK 的占位值：部分客户端要求非空字符串才肯构造。
NO_AUTH_PLACEHOLDER = "no-auth-required"


def create_chat_model(settings: Settings) -> BaseChatModel:
    """Create the DeepSeek chat model from settings."""
    return _create_deepseek_model(settings, settings.chat_model, purpose="chat")


def create_chat_model_from_config(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
) -> BaseChatModel:
    """Create a chat model from an explicit runtime configuration.

    ``provider`` uses the profile vocabulary: ``deepseek`` maps to the DeepSeek
    integration, ``openai-compatible`` is served by the openai integration pointed at
    the caller's base_url. An empty ``base_url`` leaves the SDK on its own default
    endpoint (only meaningful for DeepSeek). ``api_key`` may be empty when the caller
    has explicitly decided the endpoint needs no credential.
    """
    model_provider = "deepseek" if provider == "deepseek" else "openai"
    kwargs: dict[str, object] = {"model": model, "model_provider": model_provider}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        # base_url 是 langchain 1.x 的规范参数名；ChatDeepSeek 与 ChatOpenAI 都会把它
        # 落到各自客户端的 base_url 上。
        kwargs["base_url"] = base_url
    _logger.info("LLM client purpose=chat provider=%s model=%s", provider, model)
    return init_chat_model(**kwargs)


def build_chat_model(config: ModelConfig, spec: ProviderSpec) -> BaseChatModel:
    """Build one chat client from a model row and its provider spec.

    No provider-specific branching: the spec decides the LangChain integration, and
    connection/model parameters are passed through uniformly.
    """
    kwargs: dict[str, object] = {
        "model": config.model,
        "model_provider": spec.langchain_provider,
    }
    base_url = config.effective_base_url(spec)
    if base_url:
        kwargs["base_url"] = base_url
    if config.auth_mode == "none":
        kwargs["api_key"] = NO_AUTH_PLACEHOLDER
    else:
        key = config.api_key.get_secret_value().strip()
        if not key:
            raise InvalidProfileError("该配置要求 API Key，但当前没有可用凭据")
        kwargs["api_key"] = key
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    kwargs["timeout"] = config.timeout_s
    kwargs["max_retries"] = config.max_retries
    _logger.info(
        "LLM client purpose=chat provider=%s model=%s base_url=%s",
        config.provider,
        config.model,
        base_url or "-",
    )
    return init_chat_model(**kwargs)


def create_judge_model(
    settings: Settings, model_name: str | None = None
) -> BaseChatModel:
    """Create a Judge using an explicit effective name or JUDGE_MODEL."""
    effective_name = (model_name or settings.judge_model).strip()
    if not effective_name:
        raise ValueError("Judge model name is not set")
    return _create_deepseek_model(settings, effective_name, purpose="Judge")


def _create_deepseek_model(
    settings: Settings, model_name: str, *, purpose: str
) -> BaseChatModel:
    """Create one DeepSeek chat-compatible model without logging credentials."""
    kwargs: dict[str, object] = {
        "model": model_name,
        "model_provider": "deepseek",
        "api_key": settings.deepseek_api_key.get_secret_value(),
    }
    if settings.deepseek_api_base:
        kwargs["api_base"] = settings.deepseek_api_base
    _logger.info("LLM client purpose=%s model=%s", purpose, model_name)
    return init_chat_model(**kwargs)
