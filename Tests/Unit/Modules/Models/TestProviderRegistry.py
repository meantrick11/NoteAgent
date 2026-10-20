"""Provider registry and generic client factory contracts, without network calls."""

import pytest
from pydantic import SecretStr

from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import InvalidProfileError, ProviderNotFoundError
from NoteAgent.Modules.Models.Provider import ModelClients as factory
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry


def _config(**changes) -> ModelConfig:
    values = {
        "id": "m1",
        "label": "Model",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "auth_mode": "api_key",
        "api_key": SecretStr("secret"),
    }
    values.update(changes)
    return ModelConfig(**values)


def test_builtin_providers_are_registered():
    registry = ProviderRegistry()
    assert registry.resolve("deepseek").langchain_provider == "deepseek"
    assert registry.resolve("openai").langchain_provider == "openai"
    assert registry.resolve("openai-compatible").base_url_required is True


def test_unknown_provider_is_rejected_with_available_ids():
    with pytest.raises(ProviderNotFoundError) as exc:
        ProviderRegistry().resolve("missing")
    assert "deepseek" in exc.value.message


def test_compatible_provider_requires_base_url():
    config = _config(provider="openai-compatible", base_url="")
    with pytest.raises(InvalidProfileError, match="Base URL"):
        config.validate_for(ProviderRegistry().resolve("openai-compatible"))


def test_compatible_provider_accepts_no_auth_with_endpoint():
    config = _config(
        provider="openai-compatible",
        base_url="http://localhost:1234/v1",
        auth_mode="none",
        api_key=SecretStr(""),
    )
    config.validate_for(ProviderRegistry().resolve("openai-compatible"))


def test_deepseek_rejects_no_auth():
    config = _config(auth_mode="none", api_key=SecretStr(""))
    with pytest.raises(InvalidProfileError, match="认证方式"):
        config.validate_for(ProviderRegistry().resolve("deepseek"))


def test_api_key_provider_requires_key():
    config = _config(api_key=SecretStr(""))
    with pytest.raises(InvalidProfileError, match="API Key"):
        config.validate_for(ProviderRegistry().resolve("deepseek"))


def test_client_factory_passes_connection_and_model_parameters(monkeypatch):
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)
    config = _config(
        provider="openai-compatible",
        model="qwen2.5",
        base_url="http://localhost:1234/v1",
        temperature=0.2,
        max_tokens=1024,
        timeout_s=45,
        max_retries=3,
    )
    factory.build_chat_model(config, ProviderRegistry().resolve("openai-compatible"))
    assert captured == {
        "model": "qwen2.5",
        "model_provider": "openai",
        "base_url": "http://localhost:1234/v1",
        "api_key": "secret",
        "temperature": 0.2,
        "max_tokens": 1024,
        "timeout": 45,
        "max_retries": 3,
    }


def test_client_factory_uses_provider_default_base_url(monkeypatch):
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init_chat_model)
    factory.build_chat_model(_config(), ProviderRegistry().resolve("deepseek"))
    assert "base_url" not in captured
    assert captured["model_provider"] == "deepseek"
