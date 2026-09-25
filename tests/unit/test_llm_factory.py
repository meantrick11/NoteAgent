"""LLM factory contracts without network calls."""

from pydantic import SecretStr

from noteagent.bootstrap.settings import Settings
from noteagent.llm import factory


def test_create_judge_model_reuses_deepseek_connection(monkeypatch):
    """Judge uses its own model name with the existing DeepSeek credentials."""
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)
    settings = Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("secret"),
        deepseek_api_base="https://example.invalid",
        chat_model="chat-model",
        judge_model="judge-model",
    )

    factory.create_judge_model(settings)

    assert captured == {
        "model": "judge-model",
        "model_provider": "deepseek",
        "api_key": "secret",
        "api_base": "https://example.invalid",
    }


def test_create_judge_model_accepts_explicit_effective_name(monkeypatch):
    """A CLI can construct a fallback Judge without mutating chat settings."""
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)
    settings = Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("secret"),
        chat_model="chat-model",
        judge_model="",
    )

    factory.create_judge_model(settings, model_name="chat-model")

    assert captured["model"] == "chat-model"
    assert settings.chat_model == "chat-model"
    assert settings.judge_model == ""


def test_create_chat_model_from_config_maps_providers(monkeypatch):
    """A profile's provider vocabulary maps onto the right SDK provider."""
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)

    factory.create_chat_model_from_config(
        provider="openai-compatible",
        model="qwen2.5",
        base_url="http://localhost:1234/v1",
        api_key="ui-secret",
    )

    assert captured == {
        "model": "qwen2.5",
        "model_provider": "openai",
        "api_key": "ui-secret",
        "base_url": "http://localhost:1234/v1",
    }

    captured.clear()
    factory.create_chat_model_from_config(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://deepseek.invalid/v1",
        api_key="env-secret",
    )

    assert captured == {
        "model": "deepseek-chat",
        "model_provider": "deepseek",
        "api_key": "env-secret",
        "base_url": "https://deepseek.invalid/v1",
    }


def test_create_chat_model_from_config_omits_empty_endpoint_and_key(monkeypatch):
    """An empty base_url or key is left out so the SDK keeps its own default."""
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)

    factory.create_chat_model_from_config(
        provider="deepseek", model="deepseek-chat", base_url="", api_key=""
    )

    assert captured == {"model": "deepseek-chat", "model_provider": "deepseek"}


def test_compatible_provider_endpoint_reaches_the_client():
    """base_url must actually land on the client, not just be accepted and dropped."""
    model = factory.create_chat_model_from_config(
        provider="openai-compatible",
        model="qwen2.5",
        base_url="https://compatible.invalid/v1",
        api_key="placeholder",
    )

    assert getattr(model, "openai_api_base", None) == "https://compatible.invalid/v1"


def test_deepseek_endpoint_reaches_the_client():
    """DeepSeek accepts base_url and forwards it to its own OpenAI-compatible client."""
    model = factory.create_chat_model_from_config(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://deepseek.invalid/v1",
        api_key="placeholder",
    )

    assert getattr(model, "openai_api_base", None) == "https://deepseek.invalid/v1"
