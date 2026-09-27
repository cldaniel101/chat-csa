"""Endpoints HTTP da base de conhecimento (`/kb/*`).

Superfície admin: todas as rotas exigem a auth admin (token do `/auth/login`).
O agente nunca passa por aqui — ele fala com o cliente `chat_csa.kb` em
processo (`kb_list`/`kb_read`, somente leitura).

Rotas:
  GET  /kb/list?prefix=   caminhos disponíveis na base
  GET  /kb/file?path=     bytes originais com content-type adequado
  POST /kb/upload         multipart em lote -> um commit atômico no branch
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import JSONResponse

from ..kb import (
    KBAuthError,
    KBConfigError,
    KBError,
    KBNotFoundError,
    KBUpstreamError,
    get_kb,
)
from . import auth as auth_store

router = APIRouter(prefix="/kb", tags=["kb"])


def require_admin(authorization: Annotated[str | None, Header()] = None):
    """Dependência das rotas /kb/*: exige token admin válido (401 sem ele)."""
    return auth_store.require_auth(authorization)


def _error_status(exc: KBError) -> int:
    if isinstance(exc, KBNotFoundError):
        return 404
    if isinstance(exc, KBConfigError):
        return 503
    if isinstance(exc, (KBAuthError, KBUpstreamError)):
        return 502
    return 400


def _error_response(exc: KBError) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=_error_status(exc))


@router.get("/list")
async def kb_list_route(prefix: str = "", _user: Annotated[dict, Depends(require_admin)] = None):
    """Caminhos disponíveis na base (relativos à raiz), filtrados pelo prefixo."""
    try:
        paths = get_kb().list(prefix)
    except KBError as exc:
        return _error_response(exc)
    return {"prefix": prefix, "paths": paths}


@router.get("/file")
async def kb_file_route(path: str, _user: Annotated[dict, Depends(require_admin)] = None):
    """Bytes do arquivo original com content-type adequado (sem conversão)."""
    try:
        file = get_kb().read(path)
    except KBError as exc:
        return _error_response(exc)
    return Response(content=file.content, media_type=file.content_type)


@router.post("/upload")
async def kb_upload_route(
    files: Annotated[list[UploadFile], File()],
    _user: Annotated[dict, Depends(require_admin)] = None,
    message: Annotated[str, Form()] = "",
):
    """Upload em lote: grava tudo num único commit atômico no branch da base.

    O caminho relativo de cada arquivo vem no filename da parte. Responde por
    arquivo (ok/erro) e o sha do commit.
    """
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        payload.append((upload.filename or "", await upload.read()))
    if not payload:
        return JSONResponse({"ok": False, "error": "Nenhum arquivo no upload."}, status_code=400)

    commit_message = message.strip() or f"kb: upload de {len(payload)} arquivo(s) via /kb/upload"
    try:
        commit = get_kb().write(payload, commit_message)
    except KBError as exc:
        body = {
            "ok": False,
            "error": str(exc),
            "files": [{"path": path, "ok": False} for path, _ in payload],
        }
        return JSONResponse(body, status_code=_error_status(exc))

    return {
        "ok": True,
        "sha": commit.sha or None,
        "files": [{"path": path, "ok": True, "size": len(content)} for path, content in payload],
    }
