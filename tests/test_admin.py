"""Auth admin e CRUD `/admin/users` preservados após a remoção do painel FastHTML."""

from __future__ import annotations

from fastapi.testclient import TestClient

from chat_csa.server import auth as auth_store
from chat_csa.server.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(".consumer"))


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": "admin-teste", "password": "senha-ficticia-de-teste"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_users_requires_auth():
    client = _client()
    assert client.get("/admin/users").status_code == 401


def test_admin_users_crud():
    client = _client()
    headers = _admin_headers(client)

    listed = client.get("/admin/users", headers=headers)
    assert listed.status_code == 200
    assert any(user["username"] == "admin-teste" for user in listed.json())

    created = client.post(
        "/admin/users",
        json={"username": "tester", "password": "outra-senha-ficticia"},
        headers=headers,
    )
    assert created.status_code == 200
    uid = created.json()["id"]

    updated = client.put(f"/admin/users/{uid}", json={"role": "admin"}, headers=headers)
    assert updated.status_code == 200

    deleted = client.delete(f"/admin/users/{uid}", headers=headers)
    assert deleted.status_code == 200


def test_admin_panel_removed():
    """O painel FastHTML foi removido junto com o ingester: /admin é 404."""
    client = _client()
    assert client.get("/admin").status_code == 404


def test_raw_or_tampered_token_is_rejected():
    client = _client()
    token = _admin_headers(client)["Authorization"].removeprefix("Bearer ")

    assert client.get("/admin/users", headers={"Authorization": token}).status_code == 401
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {token}x"}).status_code == 401


def test_admin_auth_fails_closed_without_environment(monkeypatch):
    monkeypatch.delenv("CHAT_CSA_ADMIN_USERNAME")
    monkeypatch.delenv("CHAT_CSA_ADMIN_PASSWORD_HASH")
    monkeypatch.delenv("CHAT_CSA_AUTH_SECRET")
    client = _client()

    response = client.post(
        "/auth/login",
        json={"username": "admin-teste", "password": "senha-ficticia-de-teste"},
    )

    assert response.status_code == 503


def test_login_is_rate_limited_after_repeated_failures():
    client = _client()
    credentials = {"username": "admin-teste", "password": "senha-incorreta-ficticia"}

    for _ in range(5):
        assert client.post("/auth/login", json=credentials).status_code == 401

    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 429
    assert response.headers["Retry-After"]


def test_expired_token_is_rejected(monkeypatch):
    client = _client()
    headers = _admin_headers(client)
    now = auth_store.time.time()
    monkeypatch.setattr(auth_store.time, "time", lambda: now + 3601)

    assert client.get("/admin/users", headers=headers).status_code == 401


def test_login_reports_configured_session_duration():
    client = _client()

    response = client.post(
        "/auth/login",
        json={"username": "admin-teste", "password": "senha-ficticia-de-teste"},
    )

    assert response.status_code == 200
    assert response.json()["expires_in"] == 3600


def test_session_uses_eight_hour_default(monkeypatch):
    monkeypatch.delenv("CHAT_CSA_AUTH_SESSION_TTL")
    client = _client()

    response = client.post(
        "/auth/login",
        json={"username": "admin-teste", "password": "senha-ficticia-de-teste"},
    )

    assert response.status_code == 200
    assert response.json()["expires_in"] == 8 * 60 * 60


def test_primary_admin_session_survives_auth_reconfiguration():
    client = _client()
    headers = _admin_headers(client)

    # Simula uma nova instância serverless carregando a mesma configuração.
    auth_store.configure_from_env()

    assert client.get("/auth/me", headers=headers).status_code == 200


def test_cors_and_security_headers_are_restricted():
    client = _client()

    trusted = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    untrusted = client.options(
        "/auth/login",
        headers={
            "Origin": "https://origem-invalida.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    protected = client.get("/admin/users")

    assert trusted.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in untrusted.headers
    assert protected.headers["Cache-Control"] == "no-store"
    assert protected.headers["X-Content-Type-Options"] == "nosniff"
