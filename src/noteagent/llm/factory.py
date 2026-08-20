import logging

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from noteagent.bootstrap.settings import Settings

_logger = logging.getLogger(__name__)


def create_chat_model(settings: Settings) -> BaseChatModel:
    """Create the DeepSeek chat model from settings."""
    kwargs: dict[str, object] = {
        "model": settings.chat_model,
        "model_provider": "deepseek",
        "api_key": settings.deepseek_api_key.get_secret_value(),
    }
    if settings.deepseek_api_base:
        kwargs["api_base"] = settings.deepseek_api_base
    _logger.info("LLM client model=%s", settings.chat_model)
    return init_chat_model(**kwargs)
