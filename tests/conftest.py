"""Fixtures compartilhadas da suíte.

A base de conhecimento é remota; nos testes, o backend `local` aponta para um
diretório temporário e o singleton do cliente é resetado a cada teste para não
vazar cache/ambiente entre casos.
"""

from __future__ import annotations

import pytest

from chat_csa import kb


@pytest.fixture(autouse=True)
def _reset_kb_singleton():
    kb.reset_kb()
    yield
    kb.reset_kb()


@pytest.fixture
def kb_local(tmp_path, monkeypatch):
    """Backend local da base apontando para um diretório temporário vazio."""
    monkeypatch.setenv("KB_BACKEND", "local")
    monkeypatch.setenv("KB_LOCAL_PATH", str(tmp_path))
    monkeypatch.delenv("CHAT_CSA_QA_CACHE_PATHS", raising=False)
    kb.reset_kb()
    yield tmp_path
    kb.reset_kb()
