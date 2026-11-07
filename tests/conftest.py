"""Fixtures compartilhadas da suíte.

A base de conhecimento é remota; nos testes, o backend `local` aponta para um
diretório temporário e o singleton do cliente é resetado a cada teste para não
vazar cache/ambiente entre casos.
"""

from __future__ import annotations

import pytest

from chat_csa import kb
from chat_csa.server import auth as auth_store

TEST_ADMIN_PASSWORD = "senha-ficticia-de-teste"
TEST_ADMIN_PASSWORD_HASH = auth_store.hash_password(TEST_ADMIN_PASSWORD)


@pytest.fixture(autouse=True)
def _reset_kb_singleton(monkeypatch):
    monkeypatch.setenv("CHAT_CSA_ADMIN_USERNAME", "admin-teste")
    monkeypatch.setenv("CHAT_CSA_ADMIN_PASSWORD_HASH", TEST_ADMIN_PASSWORD_HASH)
    monkeypatch.setenv("CHAT_CSA_AUTH_SECRET", "segredo-ficticio-de-teste-com-mais-de-32-bytes")
    monkeypatch.setenv("CHAT_CSA_AUTH_SESSION_TTL", "3600")
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
