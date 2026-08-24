"""Entrypoint do backend chat-csa para a runtime Python da Vercel.

Expõe o app FastAPI (`chat_csa.server.app`) como função ASGI e aponta
AGENT_CONFIG_DIR para o diretório `.ingester` embutido no deploy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# src-layout: coloca <repo>/src no path antes de importar o pacote
sys.path.insert(0, str(ROOT / "src"))

# O config dir precisa resolver DENTRO do bundle da função (caminho absoluto)
os.environ.setdefault("AGENT_CONFIG_DIR", str(ROOT / ".ingester"))

from chat_csa.server.app import app  # noqa: E402

# Alias explícito: a Vercel detecta apps WSGI/ASGI expostos como `app`
handler = app
