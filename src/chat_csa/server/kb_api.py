"""Endpoints HTTP da base de conhecimento (`/kb/*`).

Superfície admin: todas as rotas exigem a auth admin (token do `/auth/login`).
O agente nunca passa por aqui — ele fala com o cliente `chat_csa.kb` em
processo (`kb_list`/`kb_read`, somente leitura).

Rotas:
  GET  /kb/list?prefix=   caminhos disponíveis na base
  GET  /kb/file?path=     bytes originais com content-type adequado
  POST /kb/upload         converte o lote em conceitos OKF -> um commit atômico
"""

from __future__ import annotations

import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..kb import (
    KBAuthError,
    KBConfigError,
    KBError,
    KBNotFoundError,
    KBUpstreamError,
    get_kb,
)
from ..kb_convert import DEFAULT_PAGES_PER_CALL, default_model_call
from ..kb_upload import DEFAULT_MAX_UPLOAD_BYTES, BatchResult, process_upload
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


def _env_int(name: str, default: int) -> int:
    """Inteiro positivo do ambiente; qualquer outra coisa vale o padrão."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _run_upload(
    payload: list[tuple[str, bytes]],
    sources: dict[str, str] | None,
    message: str,
) -> BatchResult:
    """Converte e commita o lote — roda fora do event loop."""
    return process_upload(
        get_kb(),
        payload,
        model_call=default_model_call(),
        sources=sources,
        message=message,
        pages_per_call=_env_int("KB_CONVERT_PAGES_PER_CALL", DEFAULT_PAGES_PER_CALL),
        max_bytes=_env_int("KB_UPLOAD_MAX_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
    )


@router.post("/upload")
async def kb_upload_route(
    files: Annotated[list[UploadFile], File()],
    _user: Annotated[dict, Depends(require_admin)] = None,
    message: Annotated[str, Form()] = "",
    sources: Annotated[str, Form()] = "",
):
    """Upload em lote: converte cada arquivo em conceito OKF e commita tudo.

    Cada arquivo vira `<pasta>/<slug>.md` (frontmatter do template OKF) e os
    índices (seção e raiz) entram no mesmo commit atômico; o original não é
    preservado. A resposta é aditiva: além de path/ok/size, marca `converted`
    e, quando o arquivo não converte, `error` com o motivo.

    `sources` é um JSON opcional `{"caminho declarado": "URL da fonte"}`.
    """
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        payload.append((upload.filename or "", await upload.read()))
    if not payload:
        return JSONResponse({"ok": False, "error": "Nenhum arquivo no upload."}, status_code=400)

    source_map: dict[str, str] | None = None
    if sources.strip():
        try:
            parsed = json.loads(sources)
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "error": f"sources inválido (JSON): {exc}"},
                status_code=400,
            )
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
        ):
            return JSONResponse(
                {"ok": False, "error": "sources deve ser um objeto JSON de caminho -> URL."},
                status_code=400,
            )
        source_map = parsed

    try:
        result = await run_in_threadpool(_run_upload, payload, source_map, message)
    except KBError as exc:
        body = {
            "ok": False,
            "error": str(exc),
            "files": [{"path": path, "ok": False} for path, _ in payload],
        }
        return JSONResponse(body, status_code=_error_status(exc))

    return {
        "ok": True,
        "sha": result.sha,
        "files": [file.as_dict() for file in result.files],
    }
