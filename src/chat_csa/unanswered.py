"""Registro mínimo e privado de perguntas sem evidência suficiente.

Os registros ficam fora do conteúdo consultável pelo agente e contêm somente
a pergunta sanitizada, a data e o escopo de processo/edição inferido. Dados de
rede, conta, sessão e o restante da conversa não são armazenados.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .kb import KBConfigError, KBError, KBNotFoundError, KBUpstreamError, get_kb
from .selection_scope import SelectionScope

UNANSWERED_PREFIX = ".admin/unanswered/"
_MAX_QUESTION_LENGTH = 500
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
_CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)")
_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class UnansweredQuestion:
    id: str
    question: str
    asked_at: str
    process: str | None = None
    year: int | None = None
    edition: int | None = None


def sanitize_question(question: str) -> str:
    """Remove identificadores comuns e limita o texto persistido."""
    sanitized = _URL_RE.sub("[link removido]", str(question))
    sanitized = _EMAIL_RE.sub("[e-mail removido]", sanitized)
    sanitized = _CPF_RE.sub("[documento removido]", sanitized)
    sanitized = _PHONE_RE.sub("[telefone removido]", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:_MAX_QUESTION_LENGTH].rstrip()


def _encryption_key() -> bytes:
    secret = os.getenv("CHAT_CSA_UNANSWERED_SECRET") or os.getenv("CHAT_CSA_AUTH_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise KBConfigError(
            "CHAT_CSA_UNANSWERED_SECRET ou CHAT_CSA_AUTH_SECRET deve ter ao menos 32 bytes."
        )
    return hashlib.sha256(f"chat-csa-unanswered-v1:{secret}".encode()).digest()


def _encrypt_question(question: str, record_id: str, key: bytes) -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, question.encode("utf-8"), record_id.encode("ascii"))
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _decrypt_question(value: str, record_id: str, key: bytes) -> str:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    if len(raw) < 13:
        raise ValueError("Registro criptografado inválido.")
    return AESGCM(key).decrypt(raw[:12], raw[12:], record_id.encode("ascii")).decode("utf-8")


def record_unanswered_question(
    question: str,
    scope: SelectionScope,
    *,
    now: datetime | None = None,
) -> UnansweredQuestion | None:
    """Registra uma lacuna por pergunta/dia, sem duplicar perguntas idênticas."""
    sanitized = sanitize_question(question)
    if not sanitized:
        return None

    asked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    key = _encryption_key()
    digest = hmac.new(key, sanitized.casefold().encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    record_id = f"{asked_at:%Y%m%d}-{digest}"
    path = f"{UNANSWERED_PREFIX}{record_id}.json"
    item = UnansweredQuestion(
        id=record_id,
        question=sanitized,
        asked_at=asked_at.isoformat().replace("+00:00", "Z"),
        process=scope.process,
        year=scope.year,
        edition=scope.edition,
    )

    stored = {
        "version": 1,
        "id": item.id,
        "asked_at": item.asked_at,
        "process": item.process,
        "year": item.year,
        "edition": item.edition,
        "question_encrypted": _encrypt_question(item.question, item.id, key),
    }

    with _WRITE_LOCK:
        kb = get_kb()
        if path in kb.list(UNANSWERED_PREFIX):
            return item
        for attempt in range(2):
            try:
                kb.write(
                    {path: json.dumps(stored, ensure_ascii=False, indent=2) + "\n"},
                    "chore: registra pergunta sem resposta",
                )
                break
            except KBUpstreamError:
                if attempt == 1:
                    raise
    return item


def list_unanswered_questions(limit: int = 200) -> list[UnansweredQuestion]:
    """Lista lacunas mais recentes, ignorando registros inválidos."""
    kb = get_kb()
    key = _encryption_key()
    items: list[UnansweredQuestion] = []
    for path in kb.list(UNANSWERED_PREFIX):
        if not path.startswith(UNANSWERED_PREFIX) or not path.endswith(".json"):
            continue
        try:
            payload = json.loads(kb.read(path).content.decode("utf-8"))
            record_id = str(payload["id"])
            item = UnansweredQuestion(
                id=record_id,
                question=_decrypt_question(str(payload["question_encrypted"]), record_id, key),
                asked_at=str(payload["asked_at"]),
                process=str(payload["process"]) if payload.get("process") else None,
                year=int(payload["year"]) if payload.get("year") is not None else None,
                edition=int(payload["edition"]) if payload.get("edition") is not None else None,
            )
        except (
            KBError,
            InvalidTag,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            continue
        items.append(item)
    items.sort(key=lambda item: item.asked_at, reverse=True)
    return items[: max(0, min(limit, 500))]


def delete_unanswered_question(record_id: str) -> None:
    """Remove uma lacuna já revisada pelo CSA."""
    if not re.fullmatch(r"\d{8}-[a-f0-9]{16}", record_id):
        raise KBNotFoundError("Pergunta sem resposta não encontrada.")
    get_kb().delete(
        f"{UNANSWERED_PREFIX}{record_id}.json",
        "chore: remove pergunta sem resposta revisada",
    )
