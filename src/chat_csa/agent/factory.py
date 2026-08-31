"""Fábrica de agentes: monta um agente LangChain com chamada de ferramentas
para uma raiz de config."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .prompt import build_system_prompt
from .tools import ALL_TOOLS, CSA_TOOLS, read


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> BaseChatModel:
    provider = (provider or os.getenv("LLM_PROVIDER") or "ollama").lower()
    model = model or os.getenv("LLM_MODEL") or os.getenv("MODEL") or ""

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        # Ollama Cloud exige token Bearer; Ollama local ignora headers extras.
        # A versão instalada do langchain-ollama não tem parâmetro api_key,
        # então o header vai via client_kwargs (cliente sync e async).
        extra: dict = {}
        if os.getenv("OLLAMA_API_KEY"):
            headers = {"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"}
            extra = {
                "client_kwargs": {"headers": headers},
                "async_client_kwargs": {"headers": headers},
            }

        # Reasoning/thinking: ligado por padrão (gemma4:31b-cloud suporta e
        # expõe o raciocínio via additional_kwargs["reasoning_content"]).
        # Desliga com OLLAMA_REASONING=0|false|no|off — modelos sem suporte
        # seguem o fallback da UI (só tool steps).
        reasoning = os.getenv("OLLAMA_REASONING", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )

        return ChatOllama(
            model=model or os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            reasoning=reasoning,
            **extra,
        )
    elif provider == "fake":
        # para testes/CI sem LLM — precisa de suporte a bind_tools
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        class FakeToolChatModel(FakeListChatModel):
            def bind_tools(self, tools, **kwargs):  # type: ignore[override]
                return self

        return FakeToolChatModel(responses=["fake-ok: agent is working (no LLM configured)"])
    else:
        raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (expected openai|ollama|fake)")


def tools_for_config(root: Path) -> list:
    """Lista de ferramentas para uma raiz de config.

    - Ingester (.ingester): ferramentas completas (read/write/edit/bash) + as
      de leitura do portal CSA (web_csa_fetch / web_csa_search).
    - Consumer (.consumer): somente leitura — `read` + as ferramentas CSA.
      O consumidor responde a partir do bundle; não escreve nem executa comandos.
    Override via CHAT_CSA_EXTRA_TOOLS=ingester|none.
    """
    extra = os.getenv("CHAT_CSA_EXTRA_TOOLS", "").lower()
    if extra == "none":
        return list(ALL_TOOLS)
    if root.name.startswith(".ingester") or extra == "ingester":
        return [*ALL_TOOLS, *CSA_TOOLS]
    if root.name.startswith(".consumer") or extra == "consumer":
        return [read, *CSA_TOOLS]
    return list(ALL_TOOLS)


def build_agent(
    config_dir: str | Path = ".ingester",
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

    # Ferramentas do portal CSA apenas para o agente ingester (leitura only)
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
