import os

os.environ["LLM_PROVIDER"] = "fake"

from fastapi.testclient import TestClient

from chat_csa.server.app import create_app


def _write_static_cache(path):
    path.write_text(
        """---
title: "FAQ de teste"
resource: "https://csa.uefs.br/index.php/sisu261/inicial"
last_verified: "2026-08-30"
---

## FAQ-001 — Posso usar o ENEM 2024?

**Categoria:** inscrição
**Cache:** static

**Perguntas equivalentes:**
- Vale ENEM 2024?

**Resposta:**
Sim. O ENEM 2024 pode ser utilizado no SiSU/UEFS 2026.

**Fonte:** Edital 01/2026, item 1.1.
""",
        encoding="utf-8",
    )


def test_health():
    app = create_app(".ingester")
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models():
    app = create_app(".consumer")
    c = TestClient(app)
    r = c.get("/v1/models")
    assert r.status_code == 200
    assert "data" in r.json()


def test_chat_completions_non_stream():
    app = create_app(".consumer")
    c = TestClient(app)
    r = c.post(
        "/v1/chat/completions",
        json={"model": "chat-csa", "messages": [{"role": "user", "content": "Opa"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert len(body["choices"]) == 1
    content = body["choices"][0]["message"]["content"]
    assert not content.startswith("Resposta:")
    assert "Fontes:" not in content


def test_chat_completions_stream():
    app = create_app(".ingester")
    c = TestClient(app)
    r = c.post(
        "/v1/chat/completions",
        json={"model": "chat-csa", "messages": [{"role": "user", "content": "hello"}], "stream": True},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "[DONE]" in r.text


def test_chat_completions_uses_markdown_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "faq.md"
    _write_static_cache(cache_file)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(cache_file))

    app = create_app(tmp_path / "config")
    c = TestClient(app)
    r = c.post(
        "/v1/chat/completions",
        json={"model": "chat-csa", "messages": [{"role": "user", "content": "Vale ENEM 2024?"}]},
    )

    assert r.status_code == 200
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    assert "ENEM 2024 pode ser utilizado" in content
    assert not content.startswith("Resposta:")
    assert "Fontes:" in content
    assert body["chat_csa"]["cache"]["hit"] is True


def test_chat_completions_stream_uses_markdown_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "faq.md"
    _write_static_cache(cache_file)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(cache_file))

    app = create_app(tmp_path / "config")
    c = TestClient(app)
    r = c.post(
        "/v1/chat/completions",
        json={"model": "chat-csa", "messages": [{"role": "user", "content": "Vale ENEM 2024?"}], "stream": True},
    )

    assert r.status_code == 200
    assert "ENEM 2024 pode ser utilizado" in r.text
    assert "[DONE]" in r.text


def test_ollama_chat():
    app = create_app(".consumer")
    c = TestClient(app)
    r = c.post("/api/chat", json={"model": "chat-csa", "messages": [{"role": "user", "content": "oi"}]})
    assert r.status_code == 200
    assert r.json()["done"] is True
