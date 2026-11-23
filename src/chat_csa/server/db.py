"""Camada isolada de acesso ao PostgreSQL para o painel administrativo.

Usa exclusivamente a variável de ambiente ``CHAT_CSA_DATABASE_URL`` (sem fallback
para ``DATABASE_URL``) para evitar colisão com outros projetos no mesmo ambiente.
Todas as tabelas usam prefixo ``chat_csa_`` e ``CREATE TABLE IF NOT EXISTS``.
Quando a variável não está configurada ou o banco fica indisponível, lança
``DatabaseUnavailableError`` para permitir fallback gracioso nos chamadores.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_TIMEOUT = 3
_schema_ready_url: str | None = None

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS chat_csa_admin_users (
        id TEXT PRIMARY KEY,
        username VARCHAR(64) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role VARCHAR(32) NOT NULL DEFAULT 'editor',
        is_superadmin BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        token_version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_by TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_csa_admin_users_username
        ON chat_csa_admin_users (username)
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_csa_audit_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        username VARCHAR(64) NOT NULL,
        user_role VARCHAR(32) NOT NULL,
        action VARCHAR(64) NOT NULL,
        resource_type VARCHAR(64) NOT NULL,
        resource_id TEXT,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_created_at
        ON chat_csa_audit_logs (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_user_id
        ON chat_csa_audit_logs (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_action
        ON chat_csa_audit_logs (action)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_resource
        ON chat_csa_audit_logs (resource_type, resource_id)
    """,
)


class DatabaseUnavailableError(RuntimeError):
    """Indica que o PostgreSQL não está configurado ou está temporariamente indisponível."""


def get_database_url() -> str:
    """Lê exclusivamente CHAT_CSA_DATABASE_URL (sem fallback para DATABASE_URL)."""
    return os.getenv("CHAT_CSA_DATABASE_URL", "").strip()


def is_database_configured() -> bool:
    """Informa se a conexão PostgreSQL exclusiva do painel está configurada."""
    return bool(get_database_url())


def _connect_timeout() -> int:
    raw = os.getenv("CHAT_CSA_DATABASE_TIMEOUT", "").strip()
    if not raw:
        return _DEFAULT_CONNECT_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_CONNECT_TIMEOUT
    return max(1, min(value, 30))


def _open_connection(dsn: str) -> Any:
    """Abre conexão psycopg3 com row_factory em dict e timeout curto."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - driver não instalado
        raise DatabaseUnavailableError("Driver PostgreSQL (psycopg) não instalado.") from exc

    return psycopg.connect(
        dsn,
        connect_timeout=_connect_timeout(),
        row_factory=dict_row,
    )


def ensure_schema(conn: Any, dsn: str) -> None:
    """Garante idempotentemente a existência das tabelas isoladas do painel."""
    global _schema_ready_url
    if _schema_ready_url == dsn:
        return
    with conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    conn.commit()
    _schema_ready_url = dsn


def reset_db_state() -> None:
    """Reseta o cache de inicialização do schema (usado em testes e reconfigurações)."""
    global _schema_ready_url
    _schema_ready_url = None


@contextmanager
def get_connection() -> Iterator[Any]:
    """Abre uma conexão PostgreSQL pronta com schema garantido.

    Converte erros de conexão/operacionais em ``DatabaseUnavailableError`` sem
    registrar credenciais ou DSN em logs.
    """
    dsn = get_database_url()
    if not dsn:
        raise DatabaseUnavailableError("CHAT_CSA_DATABASE_URL não configurada.")

    conn: Any = None
    try:
        conn = _open_connection(dsn)
        ensure_schema(conn, dsn)
    except DatabaseUnavailableError:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise
    except Exception as exc:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        logger.warning(
            "PostgreSQL indisponível ao abrir conexão administrativa (%s); ativando fallback.",
            type(exc).__name__,
        )
        raise DatabaseUnavailableError("PostgreSQL temporariamente indisponível.") from exc

    try:
        yield conn
        conn.commit()
    except DatabaseUnavailableError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        # Erros de integridade/domínio podem ser tratados pelo chamador; erros
        # operacionais de conexão/interface ativam fallback gracioso.
        exc_module = type(exc).__module__
        exc_name = type(exc).__name__
        if exc_module.startswith("psycopg") and exc_name in {
            "OperationalError",
            "InterfaceError",
            "DatabaseError",
        }:
            logger.warning(
                "Erro operacional no PostgreSQL (%s); ativando fallback.",
                exc_name,
            )
            raise DatabaseUnavailableError("PostgreSQL temporariamente indisponível.") from exc
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
