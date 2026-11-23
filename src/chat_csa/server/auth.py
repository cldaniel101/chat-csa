"""Autenticação e gestão de usuários do painel administrativo.

Não existe credencial padrão. O painel só é habilitado quando
``CHAT_CSA_ADMIN_USERNAME``, ``CHAT_CSA_ADMIN_PASSWORD_HASH`` e
``CHAT_CSA_AUTH_SECRET`` estão configurados. Senhas são armazenadas como hash
scrypt e as sessões são tokens assinados, com prazo de validade.

O administrador principal (``env-admin``) é sempre carregado do ambiente com
``is_superadmin=True`` e não pode ser removido, desativado ou rebaixado por
outros usuários nem por si mesmo. Usuários adicionais são persistidos no
PostgreSQL (``chat_csa_admin_users``) quando ``CHAT_CSA_DATABASE_URL`` está
configurada e disponível, com fallback seguro em memória em caso de
indisponibilidade.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from . import db

logger = logging.getLogger(__name__)

_PASSWORD_MIN_LENGTH = 12
_SESSION_TTL_DEFAULT = 8 * 60 * 60
_SESSION_TTL_MIN = 5 * 60
_SESSION_TTL_MAX = 7 * 24 * 60 * 60
_LOGIN_WINDOW_SECONDS = 5 * 60
_LOGIN_MAX_FAILURES = 5
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")
_VALID_ROLES = frozenset({"admin", "editor"})
_PANEL_ROLES = frozenset({"admin", "editor"})


@dataclass(frozen=True)
class AuthConfig:
    secret: bytes
    session_ttl: int


_config: AuthConfig | None = None
_config_error = "Autenticação administrativa não configurada."
_primary_user: dict[str, Any] | None = None
_fallback_users: list[dict[str, Any]] = []
_login_failures: dict[str, list[float]] = {}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Gera um hash scrypt apropriado para armazenamento seguro ou env."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise ValueError(f"A senha deve ter ao menos {_PASSWORD_MIN_LENGTH} caracteres.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64encode(salt)}${_b64encode(digest)}"


def _valid_password_hash(encoded: str) -> bool:
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        return (
            algorithm == "scrypt"
            and (int(n_raw), int(r_raw), int(p_raw)) == (2**14, 8, 1)
            and len(_b64decode(salt_raw)) >= 16
            and len(_b64decode(digest_raw)) == 32
        )
    except (ValueError, TypeError, binascii.Error):
        return False


def _verify_password(password: str, encoded: str) -> bool:
    if not _valid_password_hash(encoded):
        return False
    try:
        _, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        expected = _b64decode(digest_raw)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_raw),
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def configure_from_env() -> None:
    """Recarrega a configuração do ambiente e limpa usuários voláteis em memória."""
    global _config, _config_error, _primary_user, _fallback_users

    username = os.getenv("CHAT_CSA_ADMIN_USERNAME", "").strip()
    password_hash = os.getenv("CHAT_CSA_ADMIN_PASSWORD_HASH", "").strip()
    secret = os.getenv("CHAT_CSA_AUTH_SECRET", "")

    _config = None
    _primary_user = None
    _fallback_users = []
    _login_failures.clear()
    db.reset_db_state()

    if not username or not password_hash or not secret:
        _config_error = "Autenticação administrativa não configurada."
        return
    if not _USERNAME_RE.fullmatch(username):
        _config_error = "CHAT_CSA_ADMIN_USERNAME é inválido."
        return
    if not _valid_password_hash(password_hash):
        _config_error = "CHAT_CSA_ADMIN_PASSWORD_HASH é inválido."
        return
    if len(secret.encode("utf-8")) < 32:
        _config_error = "CHAT_CSA_AUTH_SECRET deve ter ao menos 32 bytes."
        return

    try:
        ttl = int(os.getenv("CHAT_CSA_AUTH_SESSION_TTL", str(_SESSION_TTL_DEFAULT)))
    except ValueError:
        _config_error = "CHAT_CSA_AUTH_SESSION_TTL deve ser um número inteiro."
        return
    if not _SESSION_TTL_MIN <= ttl <= _SESSION_TTL_MAX:
        _config_error = "CHAT_CSA_AUTH_SESSION_TTL está fora do intervalo permitido."
        return

    _config = AuthConfig(secret=secret.encode("utf-8"), session_ttl=ttl)
    _primary_user = {
        "id": "env-admin",
        "username": username,
        "password_hash": password_hash,
        "role": "admin",
        "is_superadmin": True,
        "is_active": True,
        "token_version": 1,
        "managed_by_env": True,
    }
    _config_error = ""


def _require_config() -> AuthConfig:
    if _config is None or _primary_user is None:
        raise HTTPException(status_code=503, detail=_config_error)
    return _config


def _normalize_db_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "username": str(row["username"]),
        "password_hash": str(row["password_hash"]),
        "role": str(row["role"]),
        "is_superadmin": bool(row.get("is_superadmin", False)),
        "is_active": bool(row.get("is_active", True)),
        "token_version": int(row.get("token_version", 1)),
        "managed_by_env": False,
    }


def _sanitize(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "is_superadmin": bool(user.get("is_superadmin", False)),
        "is_active": bool(user.get("is_active", True)),
        "managed_by_env": bool(user.get("managed_by_env", False)),
    }


def _is_protected_superadmin(user: dict[str, Any]) -> bool:
    return bool(user.get("managed_by_env") or user.get("is_superadmin"))


def _is_unique_violation(exc: Exception) -> bool:
    return type(exc).__name__ == "UniqueViolation" or getattr(exc, "sqlstate", None) == "23505"


def list_users() -> list[dict[str, Any]]:
    """Lista o superusuário principal e os usuários secundários (PostgreSQL ou fallback)."""
    _require_config()
    assert _primary_user is not None

    users: list[dict[str, Any]] = [_sanitize(_primary_user)]
    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, username, password_hash, role, is_superadmin, is_active, token_version
                        FROM chat_csa_admin_users
                        ORDER BY created_at ASC, username ASC
                        """
                    )
                    rows = cur.fetchall()
            for row in rows:
                normalized = _normalize_db_user(dict(row))
                if (
                    normalized["id"] == _primary_user["id"]
                    or normalized["username"] == _primary_user["username"]
                ):
                    continue
                users.append(_sanitize(normalized))
            return users
        except db.DatabaseUnavailableError:
            logger.warning("Listando usuários em modo fallback (PostgreSQL indisponível).")

    users.extend(_sanitize(user) for user in _fallback_users)
    return users


def find_user(username: str) -> dict[str, Any] | None:
    """Busca usuário por username (prioriza o superusuário do ambiente)."""
    if _primary_user and _primary_user["username"] == username:
        return _primary_user

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, username, password_hash, role, is_superadmin, is_active, token_version
                        FROM chat_csa_admin_users
                        WHERE username = %s
                        LIMIT 1
                        """,
                        (username,),
                    )
                    row = cur.fetchone()
            return _normalize_db_user(dict(row)) if row else None
        except db.DatabaseUnavailableError:
            logger.warning("Busca de usuário por username em modo fallback (PostgreSQL indisponível).")

    return next((user for user in _fallback_users if user["username"] == username), None)


def find_user_by_id(uid: str) -> dict[str, Any] | None:
    """Busca usuário por ID (prioriza o superusuário do ambiente)."""
    if _primary_user and _primary_user["id"] == uid:
        return _primary_user

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, username, password_hash, role, is_superadmin, is_active, token_version
                        FROM chat_csa_admin_users
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (uid,),
                    )
                    row = cur.fetchone()
            return _normalize_db_user(dict(row)) if row else None
        except db.DatabaseUnavailableError:
            logger.warning("Busca de usuário por id em modo fallback (PostgreSQL indisponível).")

    return next((user for user in _fallback_users if user["id"] == uid), None)


def _validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise HTTPException(status_code=400, detail="Nome de usuário inválido.")
    username = username.strip()
    if not _USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="Nome de usuário inválido.")
    return username


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < _PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"A senha deve ter ao menos {_PASSWORD_MIN_LENGTH} caracteres.",
        )


def _validate_role(role: str) -> str:
    if not isinstance(role, str) or role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Perfil de usuário inválido. Valores permitidos: 'admin' ou 'editor'.",
        )
    return role


def create_user(
    username: str,
    password: str,
    role: str = "admin",
    *,
    is_superadmin: bool = False,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Cria usuário secundário no PostgreSQL (ou fallback em memória)."""
    _require_config()
    if is_superadmin:
        raise HTTPException(
            status_code=403,
            detail="Não é permitido criar outro superadministrador pela API.",
        )
    username = _validate_username(username)
    _validate_password(password)
    role = _validate_role(role)

    if _primary_user and _primary_user["username"] == username:
        raise HTTPException(status_code=400, detail="Nome de usuário já existe.")

    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "is_superadmin": False,
        "is_active": True,
        "token_version": 1,
        "managed_by_env": False,
    }

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_csa_admin_users (
                            id, username, password_hash, role, is_superadmin,
                            is_active, token_version, created_by
                        )
                        VALUES (%s, %s, %s, %s, FALSE, TRUE, 1, %s)
                        RETURNING id, username, password_hash, role, is_superadmin, is_active, token_version
                        """,
                        (
                            user["id"],
                            user["username"],
                            user["password_hash"],
                            user["role"],
                            created_by,
                        ),
                    )
                    row = cur.fetchone()
            return _sanitize(_normalize_db_user(dict(row))) if row else _sanitize(user)
        except db.DatabaseUnavailableError:
            logger.warning("Criando usuário em modo fallback (PostgreSQL indisponível).")
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(status_code=400, detail="Nome de usuário já existe.") from exc
            raise

    if any(existing["username"] == username for existing in _fallback_users):
        raise HTTPException(status_code=400, detail="Nome de usuário já existe.")
    _fallback_users.append(user)
    return _sanitize(user)


def update_user(
    uid: str,
    username: str | None = None,
    password: str | None = None,
    role: str | None = None,
    *,
    is_active: bool | None = None,
    is_superadmin: bool | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Atualiza usuário secundário; protege incondicionalmente o superusuário."""
    _require_config()
    user = find_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if _is_protected_superadmin(user):
        raise HTTPException(
            status_code=403,
            detail="O superadministrador principal não pode ser alterado, desativado ou rebaixado.",
        )
    if is_superadmin is not None:
        raise HTTPException(
            status_code=403,
            detail="Não é permitido conceder ou alterar privilégio de superadministrador.",
        )
    if actor_id and actor_id == user["id"] and is_active is False:
        raise HTTPException(
            status_code=403,
            detail="Não é permitido desativar o próprio usuário.",
        )

    new_username = user["username"]
    if username is not None:
        new_username = _validate_username(username)
        if _primary_user and new_username == _primary_user["username"]:
            raise HTTPException(status_code=400, detail="Nome de usuário já existe.")

    new_password_hash = user["password_hash"]
    if password is not None:
        _validate_password(password)
        new_password_hash = hash_password(password)

    new_role = user["role"]
    if role is not None:
        new_role = _validate_role(role)

    new_is_active = user["is_active"]
    if is_active is not None:
        if not isinstance(is_active, bool):
            raise HTTPException(status_code=400, detail="Campo is_active inválido.")
        new_is_active = is_active

    new_token_version = user["token_version"] + 1

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE chat_csa_admin_users
                        SET username = %s,
                            password_hash = %s,
                            role = %s,
                            is_active = %s,
                            token_version = %s,
                            updated_at = NOW()
                        WHERE id = %s AND is_superadmin = FALSE
                        RETURNING id, username, password_hash, role, is_superadmin, is_active, token_version
                        """,
                        (
                            new_username,
                            new_password_hash,
                            new_role,
                            new_is_active,
                            new_token_version,
                            uid,
                        ),
                    )
                    row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
            return _sanitize(_normalize_db_user(dict(row)))
        except db.DatabaseUnavailableError:
            logger.warning("Atualizando usuário em modo fallback (PostgreSQL indisponível).")
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(status_code=400, detail="Nome de usuário já existe.") from exc
            raise

    fallback_target = next((item for item in _fallback_users if item["id"] == uid), None)
    if not fallback_target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if new_username != fallback_target["username"] and any(
        existing["username"] == new_username for existing in _fallback_users
    ):
        raise HTTPException(status_code=400, detail="Nome de usuário já existe.")

    fallback_target["username"] = new_username
    fallback_target["password_hash"] = new_password_hash
    fallback_target["role"] = new_role
    fallback_target["is_active"] = new_is_active
    fallback_target["token_version"] = new_token_version
    return _sanitize(fallback_target)


def delete_user(uid: str, *, actor_id: str | None = None) -> dict[str, Any]:
    """Remove usuário secundário; impede remoção do superusuário ou auto-exclusão."""
    _require_config()
    user = find_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if _is_protected_superadmin(user):
        raise HTTPException(
            status_code=403,
            detail="O superadministrador principal não pode ser removido.",
        )
    if actor_id and actor_id == user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Não é permitido remover o próprio usuário.",
        )

    if db.is_database_configured():
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM chat_csa_admin_users
                        WHERE id = %s AND is_superadmin = FALSE
                        RETURNING id, username, role
                        """,
                        (uid,),
                    )
                    row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
            return {
                "ok": True,
                "id": str(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
            }
        except db.DatabaseUnavailableError:
            logger.warning("Removendo usuário em modo fallback (PostgreSQL indisponível).")

    fallback_target = next((item for item in _fallback_users if item["id"] == uid), None)
    if not fallback_target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    _fallback_users.remove(fallback_target)
    return {
        "ok": True,
        "id": fallback_target["id"],
        "username": fallback_target["username"],
        "role": fallback_target["role"],
    }


def _attempt_key(client_id: str) -> str:
    return hashlib.sha256(client_id.encode()).hexdigest()


def _check_login_limit(key: str, now: float) -> None:
    failures = [attempt for attempt in _login_failures.get(key, []) if now - attempt < _LOGIN_WINDOW_SECONDS]
    _login_failures[key] = failures
    if len(failures) >= _LOGIN_MAX_FAILURES:
        retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (now - failures[0])))
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Tente novamente mais tarde.",
            headers={"Retry-After": str(retry_after)},
        )


def _issue_token(user: dict[str, Any], config: AuthConfig, now: int) -> str:
    payload = {
        "sub": user["id"],
        "usr": user["username"],
        "role": user["role"],
        "sup": bool(user.get("is_superadmin", False)),
        "ver": user["token_version"],
        "iat": now,
        "exp": now + config.session_ttl,
        "jti": secrets.token_urlsafe(12),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64encode(hmac.new(config.secret, encoded.encode(), hashlib.sha256).digest())
    return f"csa1.{encoded}.{signature}"


def login(username: str, password: str, client_id: str = "unknown") -> dict[str, Any]:
    config = _require_config()
    assert _primary_user is not None
    now = time.time()
    if not isinstance(username, str) or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Requisição de login inválida.")
    key = _attempt_key(client_id)
    _check_login_limit(key, now)

    user = find_user(username)
    candidate_hash = user["password_hash"] if user else _primary_user["password_hash"]
    password_matches = _verify_password(password, candidate_hash)
    if not user or not user.get("is_active", True) or not password_matches:
        _login_failures.setdefault(key, []).append(now)
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _login_failures.pop(key, None)
    issued_at = int(now)
    return {
        "access_token": _issue_token(user, config, issued_at),
        "token_type": "bearer",
        "expires_in": config.session_ttl,
        "user": _sanitize(user),
    }


def verify_token(authorization: str | None) -> dict[str, Any] | None:
    if _config is None or not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None

    try:
        version, payload_raw, signature_raw = token.split(".", 2)
        if version != "csa1":
            return None
        expected = hmac.new(_config.secret, payload_raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_raw)):
            return None
        payload = json.loads(_b64decode(payload_raw))
        if not isinstance(payload, dict) or int(payload["exp"]) <= int(time.time()):
            return None
        user = find_user_by_id(str(payload["sub"]))
        if not user or not user.get("is_active", True):
            return None
        if (
            payload.get("usr") != user["username"]
            or payload.get("role") != user["role"]
            or payload.get("ver") != user["token_version"]
        ):
            return None
        if "sup" in payload and bool(payload["sup"]) != bool(user.get("is_superadmin", False)):
            return None
        return _sanitize(user)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        return None


def require_auth(authorization: str | None) -> dict[str, Any]:
    """Exige sessão autenticada válida para acesso ao painel administrativo."""
    _require_config()
    user = verify_token(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.get("role") not in _PANEL_ROLES:
        raise HTTPException(status_code=403, detail="Acesso administrativo necessário.")
    return user


def require_superadmin(authorization: str | None) -> dict[str, Any]:
    """Exige o superusuário principal para ações sensíveis (gestão de usuários)."""
    user = require_auth(authorization)
    if not user.get("is_superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Apenas o superadministrador principal pode gerenciar usuários.",
        )
    return user


def require_audit_access(authorization: str | None) -> dict[str, Any]:
    """Exige superusuário ou perfil admin para leitura dos logs de auditoria."""
    user = require_auth(authorization)
    if not (user.get("is_superadmin") or user.get("role") == "admin"):
        raise HTTPException(
            status_code=403,
            detail="Acesso administrativo necessário para consultar logs de auditoria.",
        )
    return user
