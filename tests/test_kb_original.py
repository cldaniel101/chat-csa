"""Original hospedado: upload, download do original e link citado ao estudante."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_kb import _fake_github, _upload_client

CONCEITO_SEM_LINK = '---\ntype: "Documento PDF"\ntitle: "Edital"\n---\n\n# Edital\n'
CONCEITO_COM_LINK = (
    '---\ntype: "Documento PDF"\ntitle: "Edital"\n'
    'resource: "https://csa.uefs.br/edital.pdf"\nurl: "https://csa.uefs.br/edital.pdf"\n---\n\n# Edital\n'
)


def _app_client(monkeypatch, state: dict):
    import chat_csa.agent.tools as tools
    import chat_csa.server.kb_api as kb_api

    fake = _fake_github(state)
    monkeypatch.setattr(kb_api, "get_kb", lambda: fake)
    monkeypatch.setattr(tools, "get_kb", lambda: fake)
    from chat_csa.server.app import create_app

    return TestClient(create_app(".consumer")), fake


def test_upload_novo_e_download_do_original_sem_virar_markdown(monkeypatch):
    """(a) upload novo guarda original + Markdown; (b) baixar entrega o original."""
    state: dict = {}
    client, token, fake = _upload_client(monkeypatch, state)
    original = b"nome,qtd\nA,1\n"

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[("files", ("editais/Planilha Final.csv", original))],
    )
    assert response.status_code == 200
    # Markdown convertido e original coexistem; o original não foi trocado pelo .md.
    assert b"| nome | qtd |" in state["files"]["editais/Planilha-Final.md"]
    assert state["files"][".originals/editais/Planilha-Final/Planilha Final.csv"] == original

    download = client.get(
        "/kb/original",
        headers={"Authorization": f"Bearer {token}"},
        params={"path": "editais/Planilha-Final.md"},
    )
    assert download.status_code == 200
    assert download.content == original
    assert "Planilha%20Final.csv" in download.headers["content-disposition"]
    # O endpoint admin exige autenticação.
    assert client.get("/kb/original", params={"path": "editais/Planilha-Final.md"}).status_code == 401
    # O original não aparece na listagem da base.
    listed = client.get("/kb/list", headers={"Authorization": f"Bearer {token}"}).json()["paths"]
    assert not any(path.startswith(".originals/") for path in listed)
    fake.close()


def test_download_publico_so_serve_original_hospedado(monkeypatch):
    """(d)/(e) sem original -> 404 claro; caminhos fora do conceito são recusados."""
    state: dict = {
        "files": {
            "editais/com.md": CONCEITO_SEM_LINK,
            "editais/sem.md": CONCEITO_SEM_LINK,
            ".originals/editais/com/com.pdf": b"%PDF-original",
        }
    }
    client, fake = _app_client(monkeypatch, state)

    ok = client.get("/kb/download", params={"path": "editais/com.md"})
    assert ok.status_code == 200 and ok.content == b"%PDF-original"
    assert ok.headers["content-type"].startswith("application/pdf")

    sem_original = client.get("/kb/download", params={"path": "editais/sem.md"})
    assert sem_original.status_code == 404
    assert "original" in sem_original.json()["error"]

    for invalido in (".originals/editais/com/com.pdf", "editais/com.pdf", "../x.md"):
        assert client.get("/kb/download", params={"path": invalido}).status_code == 400
    fake.close()


def test_kb_read_orienta_link_do_csa_ou_download_ou_nenhum(monkeypatch):
    """(c) link do CSA; (d) download do original; (e) sem link nem original."""
    from chat_csa.agent.tools import kb_list, kb_read

    state: dict = {
        "files": {
            "editais/csa.md": CONCEITO_COM_LINK,
            "editais/hospedado.md": CONCEITO_SEM_LINK,
            "editais/nada.md": CONCEITO_SEM_LINK,
            ".originals/editais/hospedado/hospedado.pdf": b"%PDF",
        }
    }
    _client, fake = _app_client(monkeypatch, state)

    com_csa = kb_read.invoke({"path": "editais/csa.md"})
    assert "https://csa.uefs.br/edital.pdf" in com_csa
    assert "/kb/download" not in com_csa

    hospedado = kb_read.invoke({"path": "editais/hospedado.md"})
    assert "(/kb/download?path=editais/hospedado.md)" in hospedado

    nada = kb_read.invoke({"path": "editais/nada.md"})
    assert "/kb/download" not in nada
    assert "não tem link do CSA nem original hospedado" in nada

    assert ".originals" not in kb_list.invoke({"prefix": ""})
    fake.close()
