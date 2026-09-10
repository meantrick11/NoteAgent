import logging

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from noteagent.bootstrap.settings import Settings

_logger = logging.getLogger(__name__)


def create_chat_model(settings: Settings) -> BaseChatModel:
    """Create the DeepSeek chat model from settings."""
    return _create_deepseek_model(settings, settings.chat_model, purpose="chat")


def create_judge_model(settings: Settings) -> BaseChatModel:
    """Create the independently configured DeepSeek Judge model."""
    if not settings.judge_model.strip():
        raise ValueError("JUDGE_MODEL is not set")
    return _create_deepseek_model(settings, settings.judge_model, purpose="Judge")


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
