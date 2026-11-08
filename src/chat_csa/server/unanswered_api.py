"""Endpoints administrativos das perguntas sem resposta."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..kb import KBAuthError, KBConfigError, KBError, KBNotFoundError, KBUpstreamError
from ..unanswered import delete_unanswered_question, list_unanswered_questions
from . import auth as auth_store

router = APIRouter(prefix="/admin/unanswered", tags=["admin"])


def require_admin(authorization: Annotated[str | None, Header()] = None):
    return auth_store.require_auth(authorization)


def _error_response(exc: KBError) -> JSONResponse:
    if isinstance(exc, KBNotFoundError):
        status = 404
    elif isinstance(exc, KBConfigError):
        status = 503
    elif isinstance(exc, (KBAuthError, KBUpstreamError)):
        status = 502
    else:
        status = 400
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=status)


@router.get("")
async def unanswered_list(
    limit: int = 200,
    _user: Annotated[dict, Depends(require_admin)] = None,
):
    try:
        items = await run_in_threadpool(list_unanswered_questions, limit)
    except KBError as exc:
        return _error_response(exc)
    return {"questions": [asdict(item) for item in items]}


@router.delete("/{record_id}")
async def unanswered_delete(
    record_id: str,
    _user: Annotated[dict, Depends(require_admin)] = None,
):
    try:
        await run_in_threadpool(delete_unanswered_question, record_id)
    except KBError as exc:
        return _error_response(exc)
    return {"ok": True, "id": record_id}
