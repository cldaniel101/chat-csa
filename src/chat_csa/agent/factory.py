"""Fábrica de agentes: monta um agente LangChain com chamada de ferramentas
para uma raiz de config."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .prompt import build_system_prompt
from .tools import ALL_TOOLS


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

        return ChatOllama(
            model=model or os.getenv("OLLAMA_MODEL", "llama3.2"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
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

    # Prefere o novo langchain.agents.create_agent (LangChain v1)
    try:
        from langchain.agents import create_agent  # type: ignore

        agent = create_agent(llm, tools=ALL_TOOLS, system_prompt=system_prompt)
        return agent, system_prompt, root, llm
    except Exception:
        pass

    from langgraph.prebuilt import create_react_agent

    agent = create_react_agent(llm, ALL_TOOLS, prompt=system_prompt)
    return agent, system_prompt, root, llm
