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
