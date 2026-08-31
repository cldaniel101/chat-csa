"""Ponto de entrada da CLI: chat-csa

Uso:
  chat-csa --config-dir .ingester --port 8001
  chat-csa --config-dir .consumer --port 8002 --provider ollama --model gemma4:31b-cloud
  chat-csa --help
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

app = typer.Typer(add_completion=False, help="Chat CSA — LangChain agent server (OpenAI + Ollama compat)")
console = Console()


@app.command()
def serve(
    config_dir: str = typer.Option(
        ".ingester",
        "--config-dir",
        "-c",
        help="Agent config dir (like .agents). Holds AGENTS.md + skills/",
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    provider: str = typer.Option(
        None,
        "--provider",
        help="LLM provider: openai | ollama | fake (default: $LLM_PROVIDER or ollama)",
    ),
    model: str = typer.Option(None, "--model", "-m", help="Model name (default: $LLM_MODEL)"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code change"),
):
    """Start the OpenAI-compatible HTTP server for one agent."""
    # Persiste a env para a fábrica do servidor pegá-la se recarregar
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if model:
        os.environ["LLM_MODEL"] = model
    os.environ["AGENT_CONFIG_DIR"] = config_dir

    root = Path(config_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]Chat CSA agent[/]  config=[cyan]{root}[/]  -> [bold]{host}:{port}[/]")
    console.print(f"  provider=[yellow]{os.getenv('LLM_PROVIDER','ollama')}[/]  model=[yellow]{os.getenv('LLM_MODEL','(default)')}[/]")
    console.print(f"  OpenAI compat: [underline]http://{host}:{port}/v1/chat/completions[/]")
    console.print(f"  Ollama  compat: [underline]http://{host}:{port}/api/chat[/]")
    console.print(f"  Health:        [underline]http://{host}:{port}/health[/]")
    console.print(f"  Docs:          [underline]http://{host}:{port}/docs[/]")

    # Cria o app via string de factory para o reload funcionar
    # Definimos a env AGENT_CONFIG_DIR, então o app padrão a lê
    uvicorn.run(
        "chat_csa.server.app:app",
        host=host,
        port=port,
        reload=reload,
        factory=False,
        env_file=None,
    )


@app.command("print-prompt")
def print_prompt(
    config_dir: str = typer.Option(".ingester", "--config-dir", "-c"),
):
    """Imprime o system prompt composto para um config dir (para depuração)."""
    from .agent.prompt import build_system_prompt

    prompt = build_system_prompt(Path(config_dir).resolve())
    console.print(prompt)


# Retrocompat: `python -m chat_csa.cli`
def main():
    app()


if __name__ == "__main__":
    main()
