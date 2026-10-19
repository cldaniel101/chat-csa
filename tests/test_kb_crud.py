"""Testes para as operações completas do ciclo CRUD de arquivos da base (/kb/*)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from chat_csa.kb import KnowledgeBase, reset_kb
from chat_csa.server.app import create_app


def _make_client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    kb_dir = tmp_path / "kb_data"
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "editais").mkdir(parents=True, exist_ok=True)
    (kb_dir / "editais" / "edital1.md").write_text("# Edital Original", encoding="utf-8")
    (kb_dir / "editais" / "edital2.md").write_text("# Edital Dois", encoding="utf-8")

    from chat_csa.kb import KBSettings, _LocalBackend

    settings = KBSettings(backend="local", local_path=kb_dir, root="", cache_ttl=0)
    backend = _LocalBackend(settings)
    kb = KnowledgeBase(settings=settings, backend=backend)

    import chat_csa.kb as kb_module
    kb_module._kb = kb

    client = TestClient(create_app(".consumer"))
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "sudo123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def test_kb_crud_requires_auth(tmp_path: Path):
    client, _ = _make_client(tmp_path)
    assert client.put("/kb/file", json={"path": "x.md", "content": "teste"}).status_code == 401
    assert client.post("/kb/move", json={"source": "a.md", "target": "b.md"}).status_code == 401
    assert client.post("/kb/bulk-delete", json={"paths": ["a.md"]}).status_code == 401
    assert client.post("/kb/folder", json={"path": "nova-pasta"}).status_code == 401
    assert client.delete("/kb/folder?path=nova-pasta").status_code == 401


def test_kb_direct_edit(tmp_path: Path):
    client, headers = _make_client(tmp_path)

    # Leitura inicial
    res_get = client.get("/kb/file?path=editais/edital1.md", headers=headers)
    assert res_get.status_code == 200
    assert res_get.text == "# Edital Original"

    # Edição direta PUT /kb/file
    res_put = client.put(
        "/kb/file",
        json={"path": "editais/edital1.md", "content": "# Edital Atualizado sem Erros"},
        headers=headers,
    )
    assert res_put.status_code == 200
    assert res_put.json()["ok"] is True

    # Confere leitura atualizada
    res_after = client.get("/kb/file?path=editais/edital1.md", headers=headers)
    assert res_after.status_code == 200
    assert res_after.text == "# Edital Atualizado sem Erros"


def test_kb_move_and_rename(tmp_path: Path):
    client, headers = _make_client(tmp_path)

    # Renomeia/move de editais/edital1.md para manuais/manual1.md
    res_move = client.post(
        "/kb/move",
        json={"source": "editais/edital1.md", "target": "manuais/manual1.md"},
        headers=headers,
    )
    assert res_move.status_code == 200
    data = res_move.json()
    assert data["ok"] is True
    assert data["source"] == "editais/edital1.md"
    assert data["target"] == "manuais/manual1.md"

    # Origem não deve mais existir
    assert client.get("/kb/file?path=editais/edital1.md", headers=headers).status_code == 404

    # Destino deve existir com o conteúdo original
    res_dest = client.get("/kb/file?path=manuais/manual1.md", headers=headers)
    assert res_dest.status_code == 200
    assert res_dest.text == "# Edital Original"


def test_kb_bulk_delete(tmp_path: Path):
    client, headers = _make_client(tmp_path)

    # Remove em lote
    res_del = client.post(
        "/kb/bulk-delete",
        json={"paths": ["editais/edital1.md", "editais/edital2.md"]},
        headers=headers,
    )
    assert res_del.status_code == 200
    assert res_del.json()["ok"] is True
    assert len(res_del.json()["paths"]) == 2

    # Confere que ambos foram removidos
    assert client.get("/kb/file?path=editais/edital1.md", headers=headers).status_code == 404
    assert client.get("/kb/file?path=editais/edital2.md", headers=headers).status_code == 404


def test_kb_folder_lifecycle(tmp_path: Path):
    client, headers = _make_client(tmp_path)

    # Cria pasta
    res_create = client.post("/kb/folder", json={"path": "normas-2026"}, headers=headers)
    assert res_create.status_code == 200
    assert res_create.json()["ok"] is True

    # Confere .gitkeep
    res_keep = client.get("/kb/file?path=normas-2026/.gitkeep", headers=headers)
    assert res_keep.status_code == 200

    # Remove pasta
    res_del = client.delete("/kb/folder?path=normas-2026", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["ok"] is True

    # Confere que .gitkeep foi removido
    assert client.get("/kb/file?path=normas-2026/.gitkeep", headers=headers).status_code == 404
    reset_kb()


def test_kb_list_metadata_and_author(tmp_path: Path):
    client, headers = _make_client(tmp_path)

    # Grava arquivo com autor e data
    client.put(
        "/kb/file",
        json={
            "path": "editais/com_autor.md",
            "content": "---\nauthor: 'Sheila'\nuploaded_at: '2026-10-19'\n---\n# Documento de Teste",
        },
        headers=headers,
    )

    # Chama /kb/list
    res_list = client.get("/kb/list", headers=headers)
    assert res_list.status_code == 200
    data = res_list.json()
    assert "files" in data
    match = next((f for f in data["files"] if f["path"] == "editais/com_autor.md"), None)
    assert match is not None
    assert match["author"] == "Sheila"
    assert match["uploaded_at"] == "2026-10-19"

    # Chama /kb/metadata
    res_meta = client.get("/kb/metadata?path=editais/com_autor.md", headers=headers)
    assert res_meta.status_code == 200
    assert res_meta.json()["author"] == "Sheila"
    assert res_meta.json()["uploaded_at"] == "2026-10-19"
    reset_kb()
