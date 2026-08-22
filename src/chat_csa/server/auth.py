"""Auth simples para o ingester — usuários e tokens em memória.

Padrão: admin / sudo123  (conforme solicitado)
Tokens são UUIDs guardados em memória. CRUD admin protegido.
Apenas para demonstração — não é nível de produção.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException

# Repositórios em memória
_users: list[dict] = [
    {"id": "1", "username": "admin", "password": "sudo123", "role": "admin"},
]
_tokens: dict[str, dict] = {}  # token -> usuário (sem senha)


def _sanitize(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password"}


def list_users():
    return [_sanitize(u) for u in _users]


def find_user(username: str):
    for u in _users:
        if u["username"] == username:
            return u
    return None


def find_user_by_id(uid: str):
    for u in _users:
        if u["id"] == uid:
            return u
    return None


def create_user(username: str, password: str, role: str = "admin"):
    if find_user(username):
        raise HTTPException(status_code=400, detail="username already exists")
    user = {"id": str(uuid.uuid4())[:8], "username": username, "password": password, "role": role}
    _users.append(user)
    return _sanitize(user)


def update_user(uid: str, username: str | None = None, password: str | None = None, role: str | None = None):
    u = find_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    if username and username != u["username"] and find_user(username):
        raise HTTPException(status_code=400, detail="username already exists")
    if username:
        u["username"] = username
    if password:
        u["password"] = password
    if role:
        u["role"] = role
    return _sanitize(u)


def delete_user(uid: str):
    u = find_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    if len(_users) == 1:
        raise HTTPException(status_code=400, detail="cannot delete last user")
    _users.remove(u)
    # invalida os tokens desse usuário
    to_del = [t for t, usr in _tokens.items() if usr["id"] == uid]
    for t in to_del:
        del _tokens[t]
    return {"ok": True}


def login(username: str, password: str):
    u = find_user(username)
    if not u or u["password"] != password:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = f"tok-{uuid.uuid4().hex}"
    _tokens[token] = _sanitize(u)
    return {"access_token": token, "token_type": "bearer", "user": _sanitize(u)}


def verify_token(token: str | None):
    if not token:
        return None
    # aceita "Bearer <token>" ou token puro
    if token.startswith("Bearer "):
        token = token[7:]
    return _tokens.get(token)


def require_auth(token: str | None):
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
