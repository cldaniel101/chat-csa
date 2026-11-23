"""Auditoria de ações do painel administrativo (PostgreSQL + fallback seguro).

Registra operações críticas — especialmente gestão de usuários, login, upload,
exclusão e alteração de arquivos da base de conhecimento — vinculadas ao autor
autenticado. Se o PostgreSQL não estiver configurado ou ficar indisponível, o
registro degrada para buffer em memória + log estruturado sem interromper o painel.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query

from . import auth as auth_store
from . import db

logger = logging.getLogger(__name__)

_FALLBACK_MAX_EVENTS = 1000
_fallback_logs: deque[dict[str, Any]] = deque(maxlen=_FALLBACK_MAX_EVENTS)
_fallback_seq = 0

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "token",
        "access_token",
        "authorization",
    }
)

router = APIRouter(prefix="/admin/audit", tags=["admin"])


def _sanitize_details(value: Any) -> Any:
    """Remove chaves sensíveis recursivamente antes de persistir metadados."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str.casefold() in _SENSITIVE_KEYS:
                continue
            sanitized[key_str] = _sanitize_details(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_details(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return datetime.now(timezone.utc).isoformat()


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            details = {"raw": details}
    if not isinstance(details, dict):
        details = {}
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "user_role": row["user_role"],
        "action": row["action"],
        "resource_type": row["resource_type"],
        "resource_id": row.get("resource_id"),
        "details": details,
        "timestamp": _format_timestamp(row.get("created_at") or row.get("timestamp")),
    }


def clear_fallback_audit_logs() -> None:
    """Limpa o buffer em memória de auditoria (usado em testes)."""
    global _fallback_seq
    _fallback_logs.clear()
    _fallback_seq = 0


def _append_fallback(
    *,
    user_id: str,
    username: str,
    user_role: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, Any],
) -> dict[str, Any]:
    global _fallback_seq
    _fallback_seq += 1
    entry = {
        "id": _fallback_seq,
        "user_id": user_id,
        "username": username,
        "user_role": user_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _fallback_logs.appendleft(entry)
    logger.info(
        "AUDIT [fallback] user_id=%s username=%s role=%s action=%s resource=%s:%s",
        user_id,
        username,
        user_role,
        action,
        resource_type,
        resource_id or "",
    )
    return entry


def record_audit_event(
    *,
    user: dict[str, Any] | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persiste um evento de auditoria no PostgreSQL ou no fallback seguro.

    Nunca propaga erro de banco para não interromper a ação principal do painel.
    """
    user_id = str((user or {}).get("id") or "unknown")
    username = str((user or {}).get("username") or "unknown")
    user_role = str((user or {}).get("role") or "unknown")
    safe_details = _sanitize_details(details or {})
    if not isinstance(safe_details, dict):
        safe_details = {"value": safe_details}

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_csa_audit_logs (
                            user_id,
                            username,
                            user_role,
                            action,
                            resource_type,
                            resource_id,
                            details
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id, user_id, username, user_role, action,
                                  resource_type, resource_id, details, created_at
                        """,
                        (
                            user_id,
                            username,
                            user_role,
                            action,
                            resource_type,
                            resource_id,
                            json.dumps(safe_details, ensure_ascii=False, default=str),
                        ),
                    )
                    row = cur.fetchone()
            if row:
                return _normalize_row(dict(row))
        except Exception as exc:
            logger.warning(
                "Falha ao gravar auditoria no PostgreSQL (%s); usando fallback em memória.",
                type(exc).__name__,
            )

    return _append_fallback(
        user_id=user_id,
        username=username,
        user_role=user_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=safe_details,
    )


def list_audit_events(
    *,
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Consulta eventos de auditoria mais recentes (PostgreSQL ou fallback)."""
    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))

    if db.is_database_configured():
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if action:
                clauses.append("action = %s")
                params.append(action)
            if user_id:
                clauses.append("user_id = %s")
                params.append(user_id)
            if resource_type:
                clauses.append("resource_type = %s")
                params.append(resource_type)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            query = f"""
                SELECT id, user_id, username, user_role, action,
                       resource_type, resource_id, details, created_at
                FROM chat_csa_audit_logs
                {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
            """
            params.extend([bounded_limit, bounded_offset])

            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()
            return {
                "logs": [_normalize_row(dict(row)) for row in rows],
                "storage": "postgres",
            }
        except Exception as exc:
            logger.warning(
                "Falha ao consultar auditoria no PostgreSQL (%s); usando fallback em memória.",
                type(exc).__name__,
            )

    filtered = [
        entry
        for entry in _fallback_logs
        if (not action or entry["action"] == action)
        and (not user_id or entry["user_id"] == user_id)
        and (not resource_type or entry["resource_type"] == resource_type)
    ]
    sliced = filtered[bounded_offset : bounded_offset + bounded_limit]
    return {"logs": sliced, "storage": "memory_fallback"}


def require_audit_reader(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Exige superusuário ou administrador para consultar os logs de auditoria."""
    return auth_store.require_audit_access(authorization)


@router.get("")
async def audit_list_route(
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: Annotated[dict[str, Any], Depends(require_audit_reader)] = None,
) -> dict[str, Any]:
    """Lista os registros de auditoria administrativos em ordem decrescente."""
    return list_audit_events(
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )
