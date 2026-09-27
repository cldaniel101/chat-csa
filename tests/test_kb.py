"""Cliente da base (`kb.py`): backend github com API falsa e upload sem commit real.

O `httpx.MockTransport` simula a Git Data API do GitHub: nenhum commit real é
criado. O teste do endpoint cobre `/kb/upload` ponta a ponta com esse backend.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from chat_csa import kb as kb_module
from chat_csa.kb import KBConfigError, KBSettings, KnowledgeBase, _GithubBackend

REPO = "cldaniel101/chat-csa"
REF_PATH = f"/repos/{REPO}/git/ref/heads/data"


def _github_settings(**overrides) -> KBSettings:
    base = {
        "backend": "github",
        "repo": REPO,
        "branch": "data",
        "write_token": "tok",
    }
    base.update(overrides)
    return KBSettings(**base)


def _handler(state: dict):
    """Handler do MockTransport simulando a Git Data API do GitHub."""
    files = state.setdefault("files", {})

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state.setdefault("calls", []).append((request.method, path))

        if path == REF_PATH and request.method == "GET":
            return httpx.Response(200, json={"object": {"sha": "base-commit"}})
        if path == f"/repos/{REPO}/git/commits/base-commit":
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if path == f"/repos/{REPO}/git/trees/base-commit":
            tree = [{"path": name, "type": "blob"} for name in sorted(files)]
            return httpx.Response(200, json={"tree": tree, "truncated": False})
        if path.startswith(f"/repos/{REPO}/contents/"):
            rel = path[len(f"/repos/{REPO}/contents/") :]
            if rel not in files:
                return httpx.Response(404, json={"message": "not found"})
            content = files[rel]
            if isinstance(content, str):
                content = content.encode("utf-8")
            encoded = base64.b64encode(content).decode("ascii")
            return httpx.Response(200, json={"content": encoded, "encoding": "base64"})
        if path == f"/repos/{REPO}/git/blobs":
            payload = json.loads(request.content)
            state.setdefault("blobs", []).append(payload)
            return httpx.Response(201, json={"sha": f"blob-{len(state['blobs'])}"})
        if path == f"/repos/{REPO}/git/trees" and request.method == "POST":
            tree = json.loads(request.content)
            state["tree"] = tree
            # Aplica os blobs no estado local (scaffold de leituras seguintes).
            for item in tree["tree"]:
                number = int(item["sha"].rsplit("-", 1)[1])
                state["files"][item["path"]] = base64.b64decode(state["blobs"][number - 1]["content"])
            return httpx.Response(201, json={"sha": "new-tree"})
        if path == f"/repos/{REPO}/git/commits" and request.method == "POST":
            state["commit"] = json.loads(request.content)
            return httpx.Response(201, json={"sha": "new-commit"})
        if path == f"/repos/{REPO}/git/refs/heads/data" and request.method == "PATCH":
            state["ref_update"] = json.loads(request.content)
            return httpx.Response(200, json={"object": {"sha": state["ref_update"]["sha"]}})
        return httpx.Response(404, json={"message": "not found"})

    return handler


def _fake_github(state: dict, **overrides) -> KnowledgeBase:
    settings = _github_settings(**overrides)
    backend = _GithubBackend(settings, transport=httpx.MockTransport(_handler(state)))
    return KnowledgeBase(settings=settings, backend=backend)


def test_github_write_um_unico_commit_atomico():
    state: dict = {}
    kb = _fake_github(state)

    commit = kb.write({"a.md": b"# A", "b/c.csv": b"x,y\n1,2\n"}, "kb: lote")

    assert commit.sha == "new-commit"
    assert commit.paths == ("a.md", "b/c.csv")
    assert len(state["blobs"]) == 2
    assert state["tree"]["base_tree"] == "base-tree"
    assert [item["path"] for item in state["tree"]["tree"]] == ["a.md", "b/c.csv"]
    assert state["commit"]["parents"] == ["base-commit"]
    assert state["commit"]["message"] == "kb: lote"
    # A ref é atualizada uma única vez — o lote nunca fica parcial.
    ref_updates = [call for call in state["calls"] if call[0] == "PATCH"]
    assert ref_updates == [("PATCH", f"/repos/{REPO}/git/refs/heads/data")]
    assert state["ref_update"]["sha"] == "new-commit"
    kb.close()


def test_github_list_filtra_prefixo_e_raiz():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == REF_PATH:
            return httpx.Response(200, json={"object": {"sha": "c"}})
        if "/git/trees/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "bundle/perguntas-frequentes/faq.md", "type": "blob"},
                        {"path": "bundle/index.md", "type": "blob"},
                        {"path": "bundle/perguntas-frequentes", "type": "tree"},
                        {"path": "fora-do-bundle.md", "type": "blob"},
                    ]
                },
            )
        return httpx.Response(404, json={"message": "not found"})

    settings = _github_settings(root="bundle")
    kb = KnowledgeBase(settings=settings, backend=_GithubBackend(settings, transport=httpx.MockTransport(handler)))

    assert kb.list("perguntas") == ["perguntas-frequentes/faq.md"]
    assert kb.list() == ["index.md", "perguntas-frequentes/faq.md"]
    kb.close()


def test_github_read_404_vira_erro_claro():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    settings = _github_settings()
    kb = KnowledgeBase(settings=settings, backend=_GithubBackend(settings, transport=httpx.MockTransport(handler)))

    with pytest.raises(kb_module.KBNotFoundError):
        kb.read("x.md")
    kb.close()


def test_github_write_sem_token_falha_antes_de_qualquer_request():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("não deveria chamar a API sem token de escrita")

    settings = _github_settings(write_token="")
    kb = KnowledgeBase(settings=settings, backend=_GithubBackend(settings, transport=httpx.MockTransport(handler)))

    with pytest.raises(KBConfigError):
        kb.write({"a.md": b"# A"}, "kb: lote")
    kb.close()


def test_write_invalida_cache(kb_local):
    kb = KnowledgeBase(settings=KBSettings(backend="local", local_path=kb_local))

    assert kb.list() == []
    kb.write({"novo.md": b"# Novo"}, "kb: novo")

    assert kb.list() == ["novo.md"]
    assert kb.read("novo.md").content == b"# Novo"
    kb.close()


def test_upload_endpoint_com_backend_github_falso(monkeypatch):
    import chat_csa.server.kb_api as kb_api

    state: dict = {}
    fake = _fake_github(state)
    monkeypatch.setattr(kb_api, "get_kb", lambda: fake)
    monkeypatch.setattr(kb_api, "default_model_call", lambda: (lambda prompt, images: "# stub"))

    from chat_csa.server.app import create_app

    client = TestClient(create_app(".consumer"))
    token = client.post("/auth/login", json={"username": "admin", "password": "sudo123"}).json()["access_token"]

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[
            ("files", ("perguntas-frequentes/faq.md", b"# FAQ\n\nPergunta e resposta.")),
            ("files", ("cronogramas/c.csv", b"a,b\n1,2\n")),
        ],
        data={"message": "kb: lote de teste"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["sha"] == "new-commit"
    assert [(item["ok"], item["converted"]) for item in body["files"]] == [(True, True), (True, True)]
    assert state["commit"]["message"] == "kb: lote de teste"

    paths = [item["path"] for item in state["tree"]["tree"]]
    assert paths == [
        "perguntas-frequentes/faq.md",
        "cronogramas/c.md",
        "perguntas-frequentes/index.md",
        "cronogramas/index.md",
        "index.md",
    ]
    assert len(paths) == len(state["blobs"]) == 5
    # O original não é preservado: só conceitos .md e índices.
    assert all(path.endswith(".md") for path in paths)
    # Conceito com frontmatter OKF e o saudação preservada no corpo.
    concept = state["files"]["perguntas-frequentes/faq.md"].decode("utf-8")
    assert concept.startswith("---\n")
    assert 'title: "FAQ"' in concept
    assert "Pergunta e resposta." in concept
    # Índice raiz criado com a seção.
    root_index = state["files"]["index.md"].decode("utf-8")
    assert "## perguntas-frequentes" in root_index
    assert "* [FAQ](perguntas-frequentes/faq.md) - Pergunta e resposta." in root_index
    fake.close()


def _upload_client(monkeypatch, state: dict):
    """Cliente admin apontado para o backend GitHub falso, com modelo stub."""
    import chat_csa.server.kb_api as kb_api

    fake = _fake_github(state)
    monkeypatch.setattr(kb_api, "get_kb", lambda: fake)
    monkeypatch.setattr(kb_api, "default_model_call", lambda: (lambda prompt, images: "# stub"))

    from chat_csa.server.app import create_app

    client = TestClient(create_app(".consumer"))
    token = client.post("/auth/login", json={"username": "admin", "password": "sudo123"}).json()["access_token"]
    return client, token, fake


def test_upload_endpoint_resposta_aditiva_sem_eco(monkeypatch):
    state: dict = {}
    client, token, fake = _upload_client(monkeypatch, state)
    conteudo = b"# Segredo\n\nConteudo secreto do arquivo."

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[
            ("files", ("editais/segredo.txt", conteudo)),
            ("files", ("editais/planilha.xlsx", b"PK-binario")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ok", "sha", "files"}
    assert body["ok"] is True
    convertido, sem_conversao = body["files"]
    assert set(convertido) == {"path", "ok", "size", "converted"}
    assert convertido == {
        "path": "editais/segredo.txt",
        "ok": True,
        "size": len(conteudo),
        "converted": True,
    }
    assert sem_conversao["converted"] is False and "sem conversão" in sem_conversao["error"]
    # Sem eco do Markdown convertido.
    assert "Conteudo secreto" not in response.text
    # Lote misto num único commit atômico: conceito + índice da seção + raiz.
    assert [item["path"] for item in state["tree"]["tree"]] == [
        "editais/segredo.md",
        "editais/index.md",
        "index.md",
    ]
    ref_updates = [call for call in state["calls"] if call[0] == "PATCH"]
    assert ref_updates == [("PATCH", f"/repos/{REPO}/git/refs/heads/data")]
    # O arquivo sem conversão não é gravado de jeito nenhum.
    assert "editais/planilha.xlsx" not in state["files"]
    fake.close()


def test_upload_endpoint_sources_declarado_e_invalido(monkeypatch):
    state: dict = {}
    client, token, fake = _upload_client(monkeypatch, state)

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[("files", ("editais/fonte.txt", b"# Fonte\n\nCorpo."))],
        data={"sources": json.dumps({"editais/fonte.txt": "https://csa.uefs.br/fonte.pdf"})},
    )

    assert response.status_code == 200
    concept = state["files"]["editais/fonte.md"].decode("utf-8")
    assert 'resource: "https://csa.uefs.br/fonte.pdf"' in concept
    assert 'url: "https://csa.uefs.br/fonte.pdf"' in concept
    assert "# Citations" in concept
    assert "[1] [Fonte](https://csa.uefs.br/fonte.pdf)" in concept

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[("files", ("editais/fonte.txt", b"# Fonte\n\nCorpo."))],
        data={"sources": "{nao e json"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    fake.close()
