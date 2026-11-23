"""Fábrica de agentes: monta um agente LangChain com chamada de ferramentas
para uma raiz de config.

O provedor de LLM é resolvido em cascata: argumento → ``LLM_PROVIDER`` →
``openrouter``. O padrão é OpenRouter (endpoint compatível com OpenAI, modelos
com tier gratuito), configurado apenas por variáveis de ambiente.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .prompt import build_system_prompt
from .tools import ALL_TOOLS, CSA_TOOLS

# Endpoint compatível com OpenAI (mesmo formato usado pelo SDK oficial).
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# Roteador de modelos gratuitos: escolhe um modelo free disponível no momento.
OPENROUTER_DEFAULT_MODEL = "openrouter/free"


def _openrouter_llm(model: str, temperature: float) -> BaseChatModel:
    """Monta o cliente OpenRouter (API compatível com OpenAI)."""
    from langchain_openai import ChatOpenAI

    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY não configurada: defina a chave no .env (não versionado) "
            "ou nas variáveis de ambiente do deploy."
        )

    # Cabeçalhos opcionais recomendados pelo OpenRouter para atribuição no ranking.
    headers: dict[str, str] = {}
    site_url = (os.getenv("OPENROUTER_SITE_URL") or "").strip()
    app_name = (os.getenv("OPENROUTER_APP_NAME") or "").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    # Modelos de reasoning gastam tokens antes de emitir texto: sem teto explícito
    # a resposta pode voltar vazia com finish_reason="length".
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    timeout = float(os.getenv("LLM_TIMEOUT_S", "60"))

    return ChatOpenAI(
        model=model or OPENROUTER_DEFAULT_MODEL,
        temperature=temperature,
        api_key=api_key,
        base_url=(os.getenv("OPENROUTER_BASE_URL") or OPENROUTER_DEFAULT_BASE_URL).rstrip("/"),
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        default_headers=headers or None,
    )


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> BaseChatModel:
    provider = (provider or os.getenv("LLM_PROVIDER") or "openrouter").lower()
    model = model or os.getenv("LLM_MODEL") or os.getenv("MODEL") or ""

    if provider == "openrouter":
        return _openrouter_llm(model or os.getenv("OPENROUTER_MODEL", ""), temperature)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    elif provider == "fake":
        # para testes/CI sem LLM — precisa de suporte a bind_tools
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        class FakeToolChatModel(FakeListChatModel):
            def bind_tools(self, tools, **kwargs):  # type: ignore[override]
                return self

        return FakeToolChatModel(responses=["fake-ok: agent is working (no LLM configured)"])
    else:
        raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (expected openrouter|openai|fake)")


def tools_for_config(root: Path) -> list:
    """Ferramentas do agente consumer — um único conjunto.

    Base fixa: `kb_list` e `kb_read` (leitura da base remota, em processo).
    As ferramentas do portal CSA (`web_csa_*`) só entram quando
    CHAT_CSA_PORTAL_TOOLS=1 (padrão 0). Não há mais agente ingester: o
    parâmetro `root` permanece só para compatibilidade de assinatura.
    """
    portal = os.getenv("CHAT_CSA_PORTAL_TOOLS", "0").strip().lower() in {"1", "true", "yes", "on"}
    return [*ALL_TOOLS, *(CSA_TOOLS if portal else [])]


def build_agent(
    config_dir: str | Path = ".consumer",
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
):
    """Monta um agente com chamada de ferramentas ligado a uma raiz de config.

    Retorna (agent_executor, system_prompt).
    O executor é um agente ReAct que suporta .ainvoke / .astream.
    Tenta langchain.agents.create_agent primeiro; como fallback, usa langgraph.
    """
    root = Path(config_dir).resolve()
    # Se o caminho ainda não existe, mesmo assim montamos um agente com prompt de fallback
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)

    system_prompt = build_system_prompt(root)
    llm = get_llm(provider=provider, model=model, temperature=temperature)

    # Ferramentas do consumer: kb_list/kb_read (+ web_csa_* se ligadas).
    tools = tools_for_config(root)

    # Prefere o novo langchain.agents.create_agent (LangChain v1)
    try:
        from langchain.agents import create_agent  # type: ignore

        agent = create_agent(llm, tools=tools, system_prompt=system_prompt)
        return agent, system_prompt, root, llm
    except Exception:
        pass

    from langgraph.prebuilt import create_react_agent

    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent, system_prompt, root, llm
