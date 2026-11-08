"""Registro e consulta administrativa de perguntas sem resposta."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from chat_csa.agent.tools import kb_list, kb_read
from chat_csa.selection_scope import infer_selection_scope
from chat_csa.server.app import create_app
from chat_csa.unanswered import (
    list_unanswered_questions,
    record_unanswered_question,
    sanitize_question,
)


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": "admin-teste", "password": "senha-ficticia-de-teste"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_sanitize_question_removes_common_personal_data():
    question = (
        "Meu CPF 123.456.789-00, telefone (75) 99999-1234 e e-mail "
        "alguem@example.com aparecem em https://example.com/token. Qual o resultado?"
    )

    sanitized = sanitize_question(question)

    assert "123.456" not in sanitized
    assert "99999" not in sanitized
    assert "alguem@" not in sanitized
    assert "https://" not in sanitized
    assert "Qual o resultado?" in sanitized


def test_record_is_deduplicated_per_day_and_kept_out_of_agent_base(kb_local):
    scope = infer_selection_scope(["Qual o cronograma do SiSU 2027?"])
    now = datetime(2026, 11, 8, 12, 30, tzinfo=timezone.utc)

    first = record_unanswered_question("Qual o cronograma do SiSU 2027?", scope, now=now)
    second = record_unanswered_question("Qual o cronograma do SiSU 2027?", scope, now=now)
    items = list_unanswered_questions()
    agent_listing = kb_list.invoke({"prefix": ""})
    direct_read = kb_read.invoke({"path": f".admin/unanswered/{first.id}.json"})
    stored = next((kb_local / ".admin" / "unanswered").glob("*.json")).read_text(encoding="utf-8")

    assert first == second
    assert len(items) == 1
    assert items[0].process == "sisu"
    assert items[0].year == 2027
    assert ".admin" not in agent_listing
    assert direct_read == "Error: caminho administrativo reservado."
    assert "Qual o cronograma" not in stored
    assert "question_encrypted" in json.loads(stored)


def test_admin_unanswered_list_requires_auth_and_can_remove_reviewed_item(kb_local):
    scope = infer_selection_scope(["Qual o cronograma do SiSU 2027?"])
    item = record_unanswered_question("Qual o cronograma do SiSU 2027?", scope)
    assert item is not None
    client = TestClient(create_app(kb_local / "config"))

    assert client.get("/admin/unanswered").status_code == 401

    headers = _admin_headers(client)
    listed = client.get("/admin/unanswered", headers=headers)
    removed = client.delete(f"/admin/unanswered/{item.id}", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["questions"][0]["question"] == "Qual o cronograma do SiSU 2027?"
    assert removed.status_code == 200
    assert client.get("/admin/unanswered", headers=headers).json()["questions"] == []
