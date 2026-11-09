"""Avisos por e-mail sobre mudanças detectadas no portal da CSA.

Este módulo é exclusivo do backend/automação. As credenciais são lidas do
ambiente somente no momento do envio e nunca são incluídas em mensagens de
erro, logs ou no payload público do workflow.
"""

from __future__ import annotations

import html
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

EMAIL_API_URL_ENV = "CHAT_CSA_EMAIL_API_URL"
EMAIL_API_TOKEN_ENV = "CHAT_CSA_EMAIL_API_TOKEN"
NOTIFICATION_TO_ENV = "CHAT_CSA_UPDATE_NOTIFICATION_TO"
MAX_LISTED_CHANGES = 25


class UpdateNotificationError(RuntimeError):
    """Falha segura ao preparar ou enviar o aviso de atualização."""


@dataclass(frozen=True)
class EmailSettings:
    """Configuração sigilosa da API de e-mail, obtida do ambiente."""

    api_url: str
    api_token: str
    recipient: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> EmailSettings:
        source = environ if environ is not None else os.environ
        values = {
            EMAIL_API_URL_ENV: source.get(EMAIL_API_URL_ENV, "").strip(),
            EMAIL_API_TOKEN_ENV: source.get(EMAIL_API_TOKEN_ENV, "").strip(),
            NOTIFICATION_TO_ENV: source.get(NOTIFICATION_TO_ENV, "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise UpdateNotificationError("Configuração de e-mail incompleta; defina: " + ", ".join(missing))

        api_url = values[EMAIL_API_URL_ENV]
        parsed = urlparse(api_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not local_http:
            raise UpdateNotificationError("A API de e-mail deve usar HTTPS.")

        return cls(
            api_url=api_url,
            api_token=values[EMAIL_API_TOKEN_ENV],
            recipient=values[NOTIFICATION_TO_ENV],
        )


@dataclass(frozen=True)
class NotificationMessage:
    """Conteúdo já renderizado do aviso."""

    subject: str
    text: str
    html: str


def load_scrape_summary(path: Path) -> dict:
    """Lê e valida o resumo produzido por ``scrape_portal.py``."""
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UpdateNotificationError("Não foi possível ler o resumo do scrape.") from exc
    if not isinstance(summary, dict) or not isinstance(summary.get("changes"), list):
        raise UpdateNotificationError("Resumo do scrape inválido: lista de mudanças ausente.")
    return summary


def build_update_message(
    summary: Mapping[str, object],
    *,
    panel_url: str,
    run_url: str = "",
) -> NotificationMessage | None:
    """Monta o aviso; devolve ``None`` quando não houve mudança."""
    raw_changes = summary.get("changes", [])
    if not isinstance(raw_changes, list):
        raise UpdateNotificationError("Resumo do scrape inválido: mudanças devem ser uma lista.")

    changes = [change for change in raw_changes if isinstance(change, dict)]
    if not changes:
        return None

    count = len(changes)
    noun = "documento" if count == 1 else "documentos"
    verb = "precisa" if count == 1 else "precisam"
    subject = f"[Chat CSA] {count} {noun} {verb} de revisão"

    text_lines = [
        f"O monitoramento do portal da CSA detectou {count} {noun} novo(s) ou alterado(s).",
        "",
        "Revise o material coletado e faça o upload ou a substituição no painel:",
        panel_url,
        "",
        "Mudanças detectadas:",
    ]
    html_items: list[str] = []
    for change in changes[:MAX_LISTED_CHANGES]:
        kind = str(change.get("kind") or "alterado")
        title = str(change.get("title") or change.get("path") or "Documento")
        source_url = str(change.get("url") or "")
        text_item = f"- [{kind}] {title}"
        if source_url:
            text_item += f" — {source_url}"
            html_title = f'<a href="{html.escape(source_url, quote=True)}">{html.escape(title)}</a>'
        else:
            html_title = html.escape(title)
        text_lines.append(text_item)
        html_items.append(f"<li><strong>{html.escape(kind)}</strong>: {html_title}</li>")

    remaining = count - MAX_LISTED_CHANGES
    if remaining > 0:
        text_lines.append(f"- … e mais {remaining} mudança(s).")
        html_items.append(f"<li>… e mais {remaining} mudança(s).</li>")

    run_block_text = ""
    run_block_html = ""
    if run_url:
        run_block_text = f"\n\nExecução e artefato: {run_url}"
        run_block_html = (
            "<p>Consulte também a "
            f'<a href="{html.escape(run_url, quote=True)}">execução e o artefato do scrape</a>.</p>'
        )

    text_lines.append(run_block_text)
    text = "\n".join(text_lines).rstrip() + "\n"
    rendered_html = (
        f"<p>O monitoramento do portal da CSA detectou <strong>{count} {noun}</strong> "
        "novo(s) ou alterado(s).</p>"
        "<p>Revise o material coletado e faça o upload ou a substituição no "
        f'<a href="{html.escape(panel_url, quote=True)}">painel administrativo</a>.</p>'
        f"<ul>{''.join(html_items)}</ul>"
        f"{run_block_html}"
    )
    return NotificationMessage(subject=subject, text=text, html=rendered_html)


def send_update_notification(
    summary: Mapping[str, object],
    *,
    panel_url: str,
    run_url: str = "",
    settings: EmailSettings | None = None,
    client: httpx.Client | None = None,
) -> bool:
    """Envia o aviso pela API HTTP; retorna ``False`` quando nada mudou."""
    message = build_update_message(summary, panel_url=panel_url, run_url=run_url)
    if message is None:
        return False

    config = settings or EmailSettings.from_env()
    payload = {
        "token": config.api_token,
        "to": config.recipient,
        "subject": message.subject,
        "message": message.text,
    }

    owned_client = client is None
    http_client = client or httpx.Client(timeout=15, follow_redirects=True)
    try:
        response = http_client.post(config.api_url, json=payload)
    except httpx.HTTPError:
        # A exceção original pode conter a URL configurada; não a propagamos.
        raise UpdateNotificationError("Falha de rede ao chamar a API de e-mail.") from None
    finally:
        if owned_client:
            http_client.close()

    if not 200 <= response.status_code < 300:
        # O corpo da API também pode conter dados sensíveis e não vai para logs.
        raise UpdateNotificationError(f"A API de e-mail recusou o aviso (HTTP {response.status_code}).")
    return True
