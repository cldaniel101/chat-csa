import os

os.environ["LLM_PROVIDER"] = "fake"

from fastapi.testclient import TestClient

from chat_csa.server.app import create_app


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
    app = create_app(".ingester")
    c = TestClient(app)
    r = c.post(
        "/v1/chat/completions",
        json={"model": "chat-csa", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert len(body["choices"]) == 1


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


def test_ollama_chat():
    app = create_app(".consumer")
    c = TestClient(app)
    r = c.post("/api/chat", json={"model": "chat-csa", "messages": [{"role": "user", "content": "oi"}]})
    assert r.status_code == 200
    assert r.json()["done"] is True
