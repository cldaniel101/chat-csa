"""Testes do alerta de revisão após o scrape do portal."""

from __future__ import annotations

import json

import httpx
import pytest

from chat_csa.update_notification import (
    EmailSettings,
    UpdateNotificationError,
    build_update_message,
    load_scrape_summary,
    send_update_notification,
)

PANEL_URL = "https://painel.exemplo.test/admin"
RUN_URL = "https://github.com/exemplo/chat-csa/actions/runs/123"


def _summary() -> dict:
    return {
        "pages": 2,
        "written": 2,
        "errors": 0,
        "changes": [
            {
                "kind": "novo",
                "path": "knowledge/raw/novo.md",
                "url": "https://csa.uefs.br/novo",
                "title": "Novo edital",
            },
            {
                "kind": "alterado",
                "path": "knowledge/raw/cronograma.md",
                "url": "https://csa.uefs.br/cronograma",
                "title": "Cronograma",
            },
        ],
    }


def _settings() -> EmailSettings:
    return EmailSettings(
        api_url="https://email.exemplo.test/send",
        api_token="token-ficticio",
        recipient="equipe@example.test",
    )


def test_load_scrape_summary(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(_summary()), encoding="utf-8")

    assert load_scrape_summary(path)["written"] == 2


def test_build_update_message_inclui_mudancas_e_links():
    message = build_update_message(_summary(), panel_url=PANEL_URL, run_url=RUN_URL)

    assert message is not None
    assert "2 documentos" in message.subject
    assert PANEL_URL in message.text
    assert RUN_URL in message.text
    assert "Novo edital" in message.html
    assert 'href="https://csa.uefs.br/cronograma"' in message.html
    assert f'href="{PANEL_URL}"' in message.html


def test_sem_mudanca_nao_exige_configuracao_nem_chama_api():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        sent = send_update_notification(
            {"changes": []},
            panel_url=PANEL_URL,
            client=client,
        )
    finally:
        client.close()

    assert sent is False
    assert called is False


def test_send_update_notification_envia_payload_e_bearer():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(202)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        sent = send_update_notification(
            _summary(),
            panel_url=PANEL_URL,
            run_url=RUN_URL,
            settings=_settings(),
            client=client,
        )
    finally:
        client.close()

    assert sent is True
    assert captured["url"] == "https://email.exemplo.test/send"
    assert captured["authorization"] == "Bearer token-ficticio"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["to"] == "equipe@example.test"
    assert PANEL_URL in payload["html"]


def test_erro_da_api_nao_expoe_configuracao_sensivel():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    try:
        with pytest.raises(UpdateNotificationError) as captured:
            send_update_notification(
                _summary(),
                panel_url=PANEL_URL,
                settings=_settings(),
                client=client,
            )
    finally:
        client.close()

    message = str(captured.value)
    assert "503" in message
    assert "token-ficticio" not in message
    assert "equipe@example.test" not in message
    assert "email.exemplo.test" not in message


def test_email_settings_exige_tres_variaveis_e_https():
    with pytest.raises(UpdateNotificationError, match="CHAT_CSA_EMAIL_API_URL"):
        EmailSettings.from_env({})

    with pytest.raises(UpdateNotificationError, match="HTTPS"):
        EmailSettings.from_env(
            {
                "CHAT_CSA_EMAIL_API_URL": "http://email.exemplo.test/send",
                "CHAT_CSA_EMAIL_API_TOKEN": "token-ficticio",
                "CHAT_CSA_UPDATE_NOTIFICATION_TO": "equipe@example.test",
            }
        )
