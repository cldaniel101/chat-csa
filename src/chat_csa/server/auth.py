"""Autenticação do painel administrativo configurada pelo ambiente.

Não existe credencial padrão. O painel só é habilitado quando
``CHAT_CSA_ADMIN_USERNAME``, ``CHAT_CSA_ADMIN_PASSWORD_HASH`` e
``CHAT_CSA_AUTH_SECRET`` estão configurados. Senhas são armazenadas como hash
scrypt e as sessões são tokens assinados, com prazo de validade.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException

_PASSWORD_MIN_LENGTH = 12
_SESSION_TTL_DEFAULT = 8 * 60 * 60
_SESSION_TTL_MIN = 5 * 60
_SESSION_TTL_MAX = 7 * 24 * 60 * 60
_LOGIN_WINDOW_SECONDS = 5 * 60
_LOGIN_MAX_FAILURES = 5
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")


@dataclass(frozen=True)
class AuthConfig:
    secret: bytes
    session_ttl: int


_config: AuthConfig | None = None
_config_error = "Autenticação administrativa não configurada."
_users: list[dict] = []
_login_failures: dict[str, list[float]] = {}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Gera um hash scrypt apropriado para a variável de ambiente."""
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
    """Recarrega a configuração e remove usuários voláteis anteriores."""
    global _config, _config_error, _users

    username = os.getenv("CHAT_CSA_ADMIN_USERNAME", "").strip()
    password_hash = os.getenv("CHAT_CSA_ADMIN_PASSWORD_HASH", "").strip()
    secret = os.getenv("CHAT_CSA_AUTH_SECRET", "")

    _config = None
    _users = []
    _login_failures.clear()

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
    _users = [
        {
            "id": "env-admin",
            "username": username,
            "password_hash": password_hash,
            "role": "admin",
            "token_version": 1,
            "managed_by_env": True,
        }
    ]
    _config_error = ""


def _require_config() -> AuthConfig:
    if _config is None:
        raise HTTPException(status_code=503, detail=_config_error)
    return _config


def _sanitize(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def list_users() -> list[dict]:
    _require_config()
    return [_sanitize(user) for user in _users]


def find_user(username: str) -> dict | None:
    return next((user for user in _users if user["username"] == username), None)


def find_user_by_id(uid: str) -> dict | None:
    return next((user for user in _users if user["id"] == uid), None)


def _validate_username(username: str) -> str:
    username = username.strip()
    if not _USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="Nome de usuário inválido.")
    return username


def _validate_password(password: str) -> None:
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"A senha deve ter ao menos {_PASSWORD_MIN_LENGTH} caracteres.",
        )


def create_user(username: str, password: str, role: str = "admin") -> dict:
    _require_config()
    username = _validate_username(username)
    _validate_password(password)
    if role != "admin":
        raise HTTPException(status_code=400, detail="Perfil de usuário inválido.")
    if find_user(username):
        raise HTTPException(status_code=400, detail="Nome de usuário já existe.")
    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "token_version": 1,
        "managed_by_env": False,
    }
    _users.append(user)
    return _sanitize(user)


def update_user(
    uid: str,
    username: str | None = None,
    password: str | None = None,
    role: str | None = None,
) -> dict:
    _require_config()
    user = find_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.get("managed_by_env"):
        raise HTTPException(status_code=409, detail="O administrador principal é gerenciado pelo ambiente.")
    if username:
        username = _validate_username(username)
        if username != user["username"] and find_user(username):
            raise HTTPException(status_code=400, detail="Nome de usuário já existe.")
        user["username"] = username
    if password:
        _validate_password(password)
        user["password_hash"] = hash_password(password)
    if role and role != "admin":
        raise HTTPException(status_code=400, detail="Perfil de usuário inválido.")
    user["token_version"] += 1
    return _sanitize(user)


def delete_user(uid: str) -> dict:
    _require_config()
    user = find_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.get("managed_by_env"):
        raise HTTPException(status_code=409, detail="O administrador principal é gerenciado pelo ambiente.")
    _users.remove(user)
    return {"ok": True}


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


def _issue_token(user: dict, config: AuthConfig, now: int) -> str:
    payload = {
        "sub": user["id"],
        "usr": user["username"],
        "role": user["role"],
        "ver": user["token_version"],
        "iat": now,
        "exp": now + config.session_ttl,
        "jti": secrets.token_urlsafe(12),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64encode(hmac.new(config.secret, encoded.encode(), hashlib.sha256).digest())
    return f"csa1.{encoded}.{signature}"


def login(username: str, password: str, client_id: str = "unknown") -> dict:
    config = _require_config()
    now = time.time()
    if not isinstance(username, str) or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Requisição de login inválida.")
    key = _attempt_key(client_id)
    _check_login_limit(key, now)

    user = find_user(username)
    candidate_hash = user["password_hash"] if user else _users[0]["password_hash"]
    password_matches = _verify_password(password, candidate_hash)
    if not user or not password_matches:
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


def verify_token(authorization: str | None) -> dict | None:
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
        if not user:
            return None
        if (
            payload.get("usr") != user["username"]
            or payload.get("role") != user["role"]
            or payload.get("ver") != user["token_version"]
        ):
            return None
        return _sanitize(user)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        return None


def require_auth(authorization: str | None) -> dict:
    _require_config()
    user = verify_token(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso administrativo necessário.")
    return user
