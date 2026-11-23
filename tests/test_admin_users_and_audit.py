"""Testes de gerenciamento de usuários, proteção do superusuário, auditoria e PostgreSQL."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from chat_csa.kb import KBSettings, KnowledgeBase, _LocalBackend, reset_kb
from chat_csa.server import audit as audit_store
from chat_csa.server import auth as auth_store
from chat_csa.server import db, kb_api
from chat_csa.server.app import create_app


@pytest.fixture(autouse=True)
def _clean_admin_state(monkeypatch):
    """Garante isolamento entre testes (sem CHAT_CSA_DATABASE_URL nem logs residuais)."""
    monkeypatch.delenv("CHAT_CSA_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    audit_store.clear_fallback_audit_logs()
    db.reset_db_state()
    yield
    audit_store.clear_fallback_audit_logs()
    db.reset_db_state()
    reset_kb()


def _login(client: TestClient, username: str, password: str) -> dict[str, Any]:
    res = client.post("/auth/login", json={"username": username, "password": password})
    return {"status": res.status_code, "body": res.json()}


def _auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    res = _login(client, username, password)
    assert res["status"] == 200, res
    return {"Authorization": f"Bearer {res['body']['access_token']}"}


def _setup_local_kb(tmp_path: Path) -> Path:
    kb_dir = tmp_path / "kb_data"
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / ".okf" / "template").mkdir(parents=True, exist_ok=True)
    (kb_dir / ".okf" / "template" / "content.md").write_text(
        "---\n"
        "type: Documento\n"
        'title: "<titulo>"\n'
        'description: "<resumo>"\n'
        'resource: "<url>"\n'
        'url: "<url>"\n'
        'source_page: "<url>"\n'
        "tags: [geral]\n"
        'timestamp: "<AAAA-MM-DD>"\n'
        "---\n\n# <Titulo>\n",
        encoding="utf-8",
    )
    (kb_dir / "index.md").write_text("# Base\n\n## Editais\n\n", encoding="utf-8")
    (kb_dir / "editais").mkdir(parents=True, exist_ok=True)
    (kb_dir / "editais" / "edital1.md").write_text("# Edital 1\n", encoding="utf-8")
    (kb_dir / "editais" / "edital2.md").write_text("# Edital 2\n", encoding="utf-8")

    settings = KBSettings(backend="local", local_path=kb_dir, root="", cache_ttl=0)
    kb = KnowledgeBase(settings=settings, backend=_LocalBackend(settings))
    import chat_csa.kb as kb_module

    kb_module._kb = kb
    return kb_dir


# ---------------------------------------------------------------------------
# Simulador leve de PostgreSQL para validar queries SQL reais e persistência
# ---------------------------------------------------------------------------


class _FakeUniqueViolation(Exception):
    sqlstate = "23505"


class _FakePostgresState:
    def __init__(self) -> None:
        self.schema_sql: list[str] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.audit_logs: list[dict[str, Any]] = []
        self.audit_seq = 0


class _FakeCursor:
    def __init__(self, state: _FakePostgresState) -> None:
        self._state = state
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        sql = " ".join(query.strip().split())
        self._rows = []

        if sql.startswith("CREATE TABLE IF NOT EXISTS") or sql.startswith("CREATE INDEX IF NOT EXISTS"):
            self._state.schema_sql.append(sql)
            return

        if sql.startswith("INSERT INTO chat_csa_admin_users"):
            uid, username, password_hash, role, created_by = params
            if any(u["username"] == username for u in self._state.users.values()):
                raise _FakeUniqueViolation("duplicate key value violates unique constraint")
            now = datetime.now(timezone.utc)
            row = {
                "id": uid,
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "is_superadmin": False,
                "is_active": True,
                "token_version": 1,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }
            self._state.users[uid] = row
            self._rows = [dict(row)]
            return

        if sql.startswith("SELECT") and "FROM chat_csa_admin_users" in sql and "WHERE username = %s" in sql:
            username = params[0]
            match = next((dict(u) for u in self._state.users.values() if u["username"] == username), None)
            self._rows = [match] if match else []
            return

        if sql.startswith("SELECT") and "FROM chat_csa_admin_users" in sql and "WHERE id = %s" in sql:
            uid = params[0]
            match = self._state.users.get(uid)
            self._rows = [dict(match)] if match else []
            return

        if sql.startswith("SELECT") and "FROM chat_csa_admin_users" in sql and "ORDER BY" in sql:
            self._rows = [
                dict(u)
                for u in sorted(
                    self._state.users.values(),
                    key=lambda item: (item["created_at"], item["username"]),
                )
            ]
            return

        if sql.startswith("UPDATE chat_csa_admin_users"):
            new_username, new_hash, new_role, new_active, new_ver, uid = params
            target = self._state.users.get(uid)
            if not target or target["is_superadmin"]:
                self._rows = []
                return
            if any(u["username"] == new_username and u["id"] != uid for u in self._state.users.values()):
                raise _FakeUniqueViolation("duplicate key value violates unique constraint")
            target.update(
                {
                    "username": new_username,
                    "password_hash": new_hash,
                    "role": new_role,
                    "is_active": new_active,
                    "token_version": new_ver,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._rows = [dict(target)]
            return

        if sql.startswith("DELETE FROM chat_csa_admin_users"):
            uid = params[0]
            target = self._state.users.get(uid)
            if not target or target["is_superadmin"]:
                self._rows = []
                return
            del self._state.users[uid]
            self._rows = [{"id": target["id"], "username": target["username"], "role": target["role"]}]
            return

        if sql.startswith("INSERT INTO chat_csa_audit_logs"):
            user_id, username, user_role, action, resource_type, resource_id, details_json = params
            self._state.audit_seq += 1
            row = {
                "id": self._state.audit_seq,
                "user_id": user_id,
                "username": username,
                "user_role": user_role,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": json.loads(details_json),
                "created_at": datetime.now(timezone.utc),
            }
            self._state.audit_logs.append(row)
            self._rows = [dict(row)]
            return

        if "FROM chat_csa_audit_logs" in sql:
            idx = 0
            action_filter = None
            user_filter = None
            resource_filter = None
            if "action = %s" in sql:
                action_filter = params[idx]
                idx += 1
            if "user_id = %s" in sql:
                user_filter = params[idx]
                idx += 1
            if "resource_type = %s" in sql:
                resource_filter = params[idx]
                idx += 1
            limit = int(params[idx])
            offset = int(params[idx + 1])

            filtered = [
                dict(entry)
                for entry in reversed(self._state.audit_logs)
                if (not action_filter or entry["action"] == action_filter)
                and (not user_filter or entry["user_id"] == user_filter)
                and (not resource_filter or entry["resource_type"] == resource_filter)
            ]
            self._rows = filtered[offset : offset + limit]
            return

        raise AssertionError(f"SQL não esperado no simulador: {sql}")

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeConnection:
    def __init__(self, state: _FakePostgresState) -> None:
        self._state = state
        self.committed = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._state)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# 1. Login multiusuário, RBAC e proteção do superusuário
# ---------------------------------------------------------------------------


def test_multi_user_login_and_strict_superadmin_permissions():
    client = TestClient(create_app(".consumer"))

    # Login do superusuário principal
    super_login = _login(client, "admin-teste", "senha-ficticia-de-teste")
    assert super_login["status"] == 200
    assert super_login["body"]["user"]["is_superadmin"] is True
    assert super_login["body"]["user"]["role"] == "admin"
    super_headers = {"Authorization": f"Bearer {super_login['body']['access_token']}"}

    # Superusuário cria um admin secundário e um editor comum
    res_admin = client.post(
        "/admin/users",
        json={"username": "admin-secundario", "password": "senha-admin-secundario-01", "role": "admin"},
        headers=super_headers,
    )
    assert res_admin.status_code == 200
    admin_user = res_admin.json()
    assert admin_user["role"] == "admin"
    assert admin_user["is_superadmin"] is False

    res_editor = client.post(
        "/admin/users",
        json={"username": "editor-maria", "password": "senha-editor-maria-01", "role": "editor"},
        headers=super_headers,
    )
    assert res_editor.status_code == 200
    editor_user = res_editor.json()
    assert editor_user["role"] == "editor"
    assert editor_user["is_superadmin"] is False

    # Ambos os usuários secundários conseguem logar e consultar /auth/me
    admin_sec_headers = _auth_headers(client, "admin-secundario", "senha-admin-secundario-01")
    editor_headers = _auth_headers(client, "editor-maria", "senha-editor-maria-01")

    me_admin = client.get("/auth/me", headers=admin_sec_headers)
    assert me_admin.status_code == 200
    assert me_admin.json()["user"]["username"] == "admin-secundario"

    me_editor = client.get("/auth/me", headers=editor_headers)
    assert me_editor.status_code == 200
    assert me_editor.json()["user"]["username"] == "editor-maria"

    # Usuários secundários (tanto admin quanto editor) NÃO podem gerenciar usuários -> 403
    for non_super_headers in (admin_sec_headers, editor_headers):
        assert client.get("/admin/users", headers=non_super_headers).status_code == 403
        assert (
            client.post(
                "/admin/users",
                json={"username": "intruso", "password": "senha-ficticia-intruso", "role": "editor"},
                headers=non_super_headers,
            ).status_code
            == 403
        )
        assert (
            client.put(
                f"/admin/users/{editor_user['id']}",
                json={"role": "admin"},
                headers=non_super_headers,
            ).status_code
            == 403
        )
        assert client.delete(f"/admin/users/{editor_user['id']}", headers=non_super_headers).status_code == 403
        assert client.delete("/admin/users/env-admin", headers=non_super_headers).status_code == 403

    # Auditoria: editor recebe 403; admin secundário e superusuário podem consultar
    assert client.get("/admin/audit", headers=editor_headers).status_code == 403
    assert client.get("/admin/audit", headers=admin_sec_headers).status_code == 200
    assert client.get("/admin/audit", headers=super_headers).status_code == 200


def test_superadmin_cannot_be_deleted_deactivated_downgraded_or_cloned():
    client = TestClient(create_app(".consumer"))
    super_headers = _auth_headers(client, "admin-teste", "senha-ficticia-de-teste")

    # Superusuário não pode remover a si mesmo nem o env-admin
    assert client.delete("/admin/users/env-admin", headers=super_headers).status_code == 403

    # Superusuário não pode rebaixar ou desativar o env-admin
    assert client.put("/admin/users/env-admin", json={"role": "editor"}, headers=super_headers).status_code == 403
    assert client.put("/admin/users/env-admin", json={"is_active": False}, headers=super_headers).status_code == 403
    assert (
        client.put("/admin/users/env-admin", json={"password": "nova-senha-muito-longa"}, headers=super_headers).status_code
        == 403
    )

    # Não é permitido criar outro superusuário pela API
    assert (
        client.post(
            "/admin/users",
            json={
                "username": "clone-super",
                "password": "senha-clone-super-01",
                "role": "admin",
                "is_superadmin": True,
            },
            headers=super_headers,
        ).status_code
        == 403
    )

    # Não é permitido promover usuário comum para superusuário
    created = client.post(
        "/admin/users",
        json={"username": "operador-joao", "password": "senha-operador-joao-01", "role": "editor"},
        headers=super_headers,
    ).json()
    assert (
        client.put(
            f"/admin/users/{created['id']}",
            json={"is_superadmin": True},
            headers=super_headers,
        ).status_code
        == 403
    )


def test_deactivated_user_loses_session_and_cannot_login():
    client = TestClient(create_app(".consumer"))
    super_headers = _auth_headers(client, "admin-teste", "senha-ficticia-de-teste")

    created = client.post(
        "/admin/users",
        json={"username": "editor-temp", "password": "senha-editor-temp-01", "role": "editor"},
        headers=super_headers,
    ).json()
    editor_headers = _auth_headers(client, "editor-temp", "senha-editor-temp-01")
    assert client.get("/auth/me", headers=editor_headers).status_code == 200

    # Superusuário desativa o usuário
    upd = client.put(
        f"/admin/users/{created['id']}",
        json={"is_active": False},
        headers=super_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["is_active"] is False

    # Token antigo é invalidado e novo login é recusado
    assert client.get("/auth/me", headers=editor_headers).status_code == 401
    assert _login(client, "editor-temp", "senha-editor-temp-01")["status"] == 401


# ---------------------------------------------------------------------------
# 2. Auditoria obrigatória de upload, exclusão e mutações de arquivos e usuários
# ---------------------------------------------------------------------------


def test_audit_records_file_upload_delete_and_user_operations_with_author(tmp_path: Path, monkeypatch):
    _setup_local_kb(tmp_path)
    monkeypatch.setattr(kb_api, "default_model_call", lambda: (lambda prompt, images: "# Conteúdo"))

    client = TestClient(create_app(".consumer"))
    super_headers = _auth_headers(client, "admin-teste", "senha-ficticia-de-teste")

    # Cria usuário secundário (editor) e faz login com ele
    editor = client.post(
        "/admin/users",
        json={"username": "curadora-ana", "password": "senha-curadora-ana-01", "role": "editor"},
        headers=super_headers,
    ).json()
    editor_headers = _auth_headers(client, "curadora-ana", "senha-curadora-ana-01")

    # 1) Upload de arquivo realizado pela usuária secundária
    upload_res = client.post(
        "/kb/upload",
        files=[("files", ("editais/Edital 2027.txt", b"Texto do edital 2027", "text/plain"))],
        data={"message": "upload edital 2027"},
        headers=editor_headers,
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["ok"] is True

    # 2) Edição direta e exclusão para lixeira feitas pela usuária secundária
    edit_res = client.put(
        "/kb/file",
        json={"path": "editais/edital1.md", "content": "# Edital 1 Revisado"},
        headers=editor_headers,
    )
    assert edit_res.status_code == 200

    soft_del = client.delete("/kb/file?path=editais/edital1.md", headers=editor_headers)
    assert soft_del.status_code == 200

    # 3) Exclusão permanente feita pelo superusuário
    perm_del = client.delete("/kb/file?path=editais/edital2.md&permanent=true", headers=super_headers)
    assert perm_del.status_code == 200

    # 4) Remoção do usuário secundário feita pelo superusuário
    del_user = client.delete(f"/admin/users/{editor['id']}", headers=super_headers)
    assert del_user.status_code == 200

    # Consulta logs de auditoria
    audit_res = client.get("/admin/audit?limit=50", headers=super_headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()["logs"]

    # Valida registro explícito de upload com autora = curadora-ana
    upload_logs = [entry for entry in logs if entry["action"] == "kb.file.upload"]
    assert len(upload_logs) == 1
    assert upload_logs[0]["user_id"] == editor["id"]
    assert upload_logs[0]["username"] == "curadora-ana"
    assert upload_logs[0]["resource_type"] == "kb_file"
    assert upload_logs[0]["resource_id"] == "editais/Edital 2027.txt"
    assert upload_logs[0]["details"]["file_name"] == "editais/Edital 2027.txt"
    assert upload_logs[0]["timestamp"]

    # Valida registro explícito de exclusão (soft delete) com autora = curadora-ana
    soft_del_logs = [entry for entry in logs if entry["action"] == "kb.file.delete"]
    assert len(soft_del_logs) == 1
    assert soft_del_logs[0]["username"] == "curadora-ana"
    assert soft_del_logs[0]["resource_id"] == "editais/edital1.md"
    assert soft_del_logs[0]["details"]["trashed"] is True

    # Valida registro explícito de exclusão permanente com autor = admin-teste
    perm_del_logs = [entry for entry in logs if entry["action"] == "kb.file.delete_permanent"]
    assert len(perm_del_logs) == 1
    assert perm_del_logs[0]["username"] == "admin-teste"
    assert perm_del_logs[0]["resource_id"] == "editais/edital2.md"
    assert perm_del_logs[0]["details"]["permanent"] is True

    # Valida que filtro por action e user_id funciona
    filtered = client.get(
        f"/admin/audit?action=kb.file.upload&user_id={editor['id']}",
        headers=super_headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()["logs"]) == 1

    # Valida criação e remoção de usuário auditadas (sem vazar senha nos detalhes)
    user_create_logs = [entry for entry in logs if entry["action"] == "user.create"]
    assert len(user_create_logs) == 1
    assert user_create_logs[0]["username"] == "admin-teste"
    assert "password" not in json.dumps(user_create_logs[0]["details"])

    user_delete_logs = [entry for entry in logs if entry["action"] == "user.delete"]
    assert len(user_delete_logs) == 1
    assert user_delete_logs[0]["resource_id"] == editor["id"]


# ---------------------------------------------------------------------------
# 3. Isolamento da env var, SQL idempotente, PostgreSQL e fallback gracioso
# ---------------------------------------------------------------------------


def test_database_config_uses_exclusively_chat_csa_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://outro-projeto:segredo@localhost:5432/outro")
    monkeypatch.delenv("CHAT_CSA_DATABASE_URL", raising=False)
    assert db.is_database_configured() is False

    monkeypatch.setenv("CHAT_CSA_DATABASE_URL", "postgresql://csa:segredo@localhost:5432/csa")
    assert db.is_database_configured() is True


def test_sql_migration_file_is_isolated_and_idempotent():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "001_chat_csa_admin_audit.sql"
    content = sql_path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS chat_csa_admin_users" in content
    assert "CREATE TABLE IF NOT EXISTS chat_csa_audit_logs" in content
    assert "DROP TABLE" not in content.upper()
    assert "ALTER TABLE" not in content.upper()


def test_postgres_persistence_flow_survives_reconfiguration(tmp_path: Path, monkeypatch):
    _setup_local_kb(tmp_path)
    fake_state = _FakePostgresState()
    monkeypatch.setenv("CHAT_CSA_DATABASE_URL", "postgresql://usuario:senha-ficticia@localhost:5432/csa_test")
    monkeypatch.setattr(db, "_open_connection", lambda dsn: _FakeConnection(fake_state))

    client = TestClient(create_app(".consumer"))
    super_headers = _auth_headers(client, "admin-teste", "senha-ficticia-de-teste")

    # Cria usuário secundário no PostgreSQL
    created = client.post(
        "/admin/users",
        json={"username": "editor-pg", "password": "senha-editor-pg-01", "role": "editor"},
        headers=super_headers,
    )
    assert created.status_code == 200
    uid = created.json()["id"]
    assert uid in fake_state.users
    assert fake_state.users[uid]["password_hash"].startswith("scrypt$")
    assert any("CREATE TABLE IF NOT EXISTS chat_csa_admin_users" in stmt for stmt in fake_state.schema_sql)
    assert any("CREATE TABLE IF NOT EXISTS chat_csa_audit_logs" in stmt for stmt in fake_state.schema_sql)

    # Simula reinicialização / nova instância serverless: usuário persiste no PostgreSQL!
    auth_store.configure_from_env()
    editor_headers = _auth_headers(client, "editor-pg", "senha-editor-pg-01")
    assert client.get("/auth/me", headers=editor_headers).status_code == 200

    # Exclusão de arquivo pelo usuário persistido grava auditoria no PostgreSQL
    del_res = client.delete("/kb/file?path=editais/edital1.md", headers=editor_headers)
    assert del_res.status_code == 200

    audit_res = client.get("/admin/audit", headers=super_headers)
    assert audit_res.status_code == 200
    assert audit_res.json()["storage"] == "postgres"
    assert any(
        entry["action"] == "kb.file.delete"
        and entry["username"] == "editor-pg"
        and entry["resource_id"] == "editais/edital1.md"
        for entry in audit_res.json()["logs"]
    )

    # Remoção de usuário remove do PostgreSQL
    assert client.delete(f"/admin/users/{uid}", headers=super_headers).status_code == 200
    assert uid not in fake_state.users


def test_graceful_fallback_when_postgres_is_unavailable(tmp_path: Path, monkeypatch, caplog):
    _setup_local_kb(tmp_path)
    secret_dsn = "postgresql://usuario:super-segredo-ficticio@127.0.0.1:1/inexistente"
    monkeypatch.setenv("CHAT_CSA_DATABASE_URL", secret_dsn)

    def _failing_connect(_dsn: str) -> Any:
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(db, "_open_connection", _failing_connect)

    with caplog.at_level(logging.WARNING):
        client = TestClient(create_app(".consumer"))

        # Superusuário continua autenticando mesmo com PostgreSQL fora do ar
        super_headers = _auth_headers(client, "admin-teste", "senha-ficticia-de-teste")

        # Operação de arquivo não quebra e registra auditoria no fallback
        del_res = client.delete("/kb/file?path=editais/edital1.md", headers=super_headers)
        assert del_res.status_code == 200

        # Consulta de auditoria degrada graciosamente para memória
        audit_res = client.get("/admin/audit", headers=super_headers)
        assert audit_res.status_code == 200
        assert audit_res.json()["storage"] == "memory_fallback"
        assert any(
            entry["action"] == "kb.file.delete" and entry["resource_id"] == "editais/edital1.md"
            for entry in audit_res.json()["logs"]
        )

        # Gestão de usuários degrada sem derrubar o painel (500)
        listed = client.get("/admin/users", headers=super_headers)
        assert listed.status_code == 200
        assert any(u["username"] == "admin-teste" for u in listed.json())

    # Nenhum segredo/DSN deve aparecer nos logs
    assert "super-segredo-ficticio" not in caplog.text
