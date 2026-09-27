"""Cliente da base (`kb.py`): backend github com API falsa e upload sem commit real.

O `httpx.MockTransport` simula a Git Data API do GitHub: nenhum commit real é
criado. O teste do endpoint cobre `/kb/upload` ponta a ponta com esse backend.
"""

from __future__ import annotations

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

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state.setdefault("calls", []).append((request.method, path))

        if path == REF_PATH and request.method == "GET":
            return httpx.Response(200, json={"object": {"sha": "base-commit"}})
        if path == f"/repos/{REPO}/git/commits/base-commit":
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if path == f"/repos/{REPO}/git/blobs":
            payload = json.loads(request.content)
            state.setdefault("blobs", []).append(payload)
            return httpx.Response(201, json={"sha": f"blob-{len(state['blobs'])}"})
        if path == f"/repos/{REPO}/git/trees" and request.method == "POST":
            state["tree"] = json.loads(request.content)
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

    from chat_csa.server.app import create_app

    client = TestClient(create_app(".consumer"))
    token = client.post("/auth/login", json={"username": "admin", "password": "sudo123"}).json()["access_token"]

    response = client.post(
        "/kb/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=[
            ("files", ("perguntas-frequentes/faq.md", b"# FAQ")),
            ("files", ("cronogramas/c.csv", b"a,b\n1,2\n")),
        ],
        data={"message": "kb: lote de teste"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["sha"] == "new-commit"
    assert [item["ok"] for item in body["files"]] == [True, True]
    assert state["commit"]["message"] == "kb: lote de teste"
    assert len(state["blobs"]) == 2
    fake.close()
