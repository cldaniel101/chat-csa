"""Auth admin e CRUD `/admin/users` preservados após a remoção do painel FastHTML."""

from __future__ import annotations

from fastapi.testclient import TestClient

from chat_csa.server.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(".consumer"))


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "admin", "password": "sudo123"})
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
    assert any(user["username"] == "admin" for user in listed.json())

    created = client.post("/admin/users", json={"username": "tester", "password": "pw"}, headers=headers)
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
