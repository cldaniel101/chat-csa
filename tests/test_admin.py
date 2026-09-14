"""Regressão: o painel admin não pode gravar `.sesskey` no diretório de trabalho.

Na Vercel a função roda em `/var/task` (somente leitura) e o `FastHTML()`
tentava gravar `.sesskey` no cwd durante o import — o que derrubava todas as
rotas com `FUNCTION_INVOCATION_FAILED`.
"""

from __future__ import annotations

from chat_csa.server.admin import build_admin_panel


def test_admin_panel_escreve_chave_em_caminho_gravavel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CHAT_CSA_ADMIN_SECRET_KEY", raising=False)
    monkeypatch.setenv("CHAT_CSA_ADMIN_KEY_FILE", str(tmp_path / ".sesskey"))

    build_admin_panel()

    assert (tmp_path / ".sesskey").exists()


def test_admin_panel_com_secret_key_do_ambiente_nao_cria_arquivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHAT_CSA_ADMIN_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("CHAT_CSA_ADMIN_KEY_FILE", str(tmp_path / ".sesskey"))

    build_admin_panel()

    assert not (tmp_path / ".sesskey").exists()


def test_admin_panel_padrao_nao_grava_no_cwd(tmp_path, monkeypatch):
    """O default não pode ser o diretório de trabalho (somente-leitura na Vercel)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CHAT_CSA_ADMIN_SECRET_KEY", raising=False)
    monkeypatch.delenv("CHAT_CSA_ADMIN_KEY_FILE", raising=False)

    build_admin_panel()

    assert not (tmp_path / ".sesskey").exists()
