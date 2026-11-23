"""Testes da fábrica de LLM: provedor padrão OpenRouter e falha explícita sem chave."""

from __future__ import annotations

import pytest

from chat_csa.agent import factory


def _clear_llm_env(monkeypatch):
    for name in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "MODEL",
        "OPENROUTER_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_SITE_URL",
        "OPENROUTER_APP_NAME",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "LLM_MAX_TOKENS",
        "LLM_TIMEOUT_S",
        "LLM_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_provider_is_openrouter(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-ficticia-de-teste")

    llm = factory.get_llm()

    assert llm.model_name == factory.OPENROUTER_DEFAULT_MODEL
    assert str(llm.openai_api_base).rstrip("/") == factory.OPENROUTER_DEFAULT_BASE_URL


def test_openrouter_requires_api_key(monkeypatch):
    _clear_llm_env(monkeypatch)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        factory.get_llm()


def test_openrouter_respects_model_and_headers(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-ficticia-de-teste")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Chat CSA")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://chat-csa-web.vercel.app")

    llm = factory.get_llm(model="openrouter/free")

    assert llm.model_name == "openrouter/free"
    assert llm.default_headers == {
        "HTTP-Referer": "https://chat-csa-web.vercel.app",
        "X-Title": "Chat CSA",
    }


def test_groq_is_not_a_supported_provider(monkeypatch):
    """O handover antigo listava `groq`; só openrouter|openai|fake são aceitos."""
    _clear_llm_env(monkeypatch)

    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        factory.get_llm(provider="groq")
