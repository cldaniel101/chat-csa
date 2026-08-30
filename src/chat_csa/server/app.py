"""Servidor FastAPI — compatível com OpenAI e com Ollama.

Endpoints:
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions   (stream e non-stream)
  POST /api/chat              (shim de compatibilidade com o Ollama)
  POST /v1/completions        (opcional, não implementado — retorna 501 se chamado)

O servidor é stateless por request; o system prompt é recarregado da
raiz de config (AGENT_CONFIG_DIR / --config-dir) a cada chamada, para que
dá para editar .ingester/AGENTS.md ou skills sem reiniciar.

Execução:
  uv run chat-csa --config-dir .ingester --port 8001
  uv run chat-csa --config-dir .consumer --port 8002
  # ou
  AGENT_CONFIG_DIR=.ingester uv run uvicorn chat_csa.server.app:create_app --factory --port 8001
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# Tipos de mensagem do LangChain
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..agent.factory import build_agent
from ..agent.prompt import build_system_prompt
from ..qa_cache import QACacheHit, lookup_cached_answer
from . import auth as auth_store
from .models import ChatMessage, ModelCard, ModelsResponse

load_dotenv()


def _openai_messages_to_lc(messages: list[ChatMessage], system_prompt: str):
    lc = []
    # Sempre antepõe o system prompt composto
    lc.append(SystemMessage(content=system_prompt))
    for m in messages:
        content = m.content
        # A OpenAI pode enviar content como lista de partes; achata para string
        if isinstance(content, list):
            # ex.: [{"type":"text","text":"hi"}]
            texts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    texts.append(str(part["text"]))
                else:
                    texts.append(str(part))
            content = "\n".join(texts)
        content = "" if content is None else str(content)
        if m.role == "system":
            lc.append(SystemMessage(content=content))
        elif m.role == "user":
            lc.append(HumanMessage(content=content))
        elif m.role == "assistant":
            # Preserva tool calls, se presentes
            if m.tool_calls:
                lc.append(AIMessage(content=content, tool_calls=m.tool_calls))  # type: ignore
            else:
                lc.append(AIMessage(content=content))
        elif m.role == "tool":
            lc.append(ToolMessage(content=content, tool_call_id=m.tool_call_id or "tool"))
        else:
            lc.append(HumanMessage(content=content))
    return lc


def _message_content_to_text(content) -> str:
    """Converte conteúdo OpenAI/Ollama em texto plano para busca no cache."""
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                texts.append(str(part["text"]))
            else:
                texts.append(str(part))
        return "\n".join(texts)
    return "" if content is None else str(content)


def _last_user_message_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return _message_content_to_text(message.content)
    return ""


def _cache_metadata(hit: QACacheHit) -> dict:
    return {
        "hit": True,
        "id": hit.entry.entry_id,
        "score": round(hit.score, 3),
        "matched_question": hit.matched_question,
        "path": str(hit.entry.path),
    }


def _extract_text_from_agent_result(result: dict) -> str:
    # O agente ReAct retorna {"messages": [ ... ]}
    msgs = result.get("messages", [])
    if not msgs:
        return ""
    last = msgs[-1]
    # Pode ser AIMessage ou dict
    if isinstance(last, dict):
        return str(last.get("content", ""))
    content = getattr(last, "content", "")
    if isinstance(content, list):
        # lista de blocos de conteúdo
        parts = []
        for c in content:
            if isinstance(c, dict) and "text" in c:
                parts.append(c["text"])
            elif isinstance(c, str):
                parts.append(c)
            else:
                parts.append(str(c))
        return "".join(parts)
    return str(content)


SENSITIVE_KEYWORDS = {
    "classificação",
    "classificacao",
    "concorrência",
    "concorrencia",
    "convocação",
    "convocacao",
    "corte",
    "curso",
    "documento",
    "documentos",
    "edital",
    "enem",
    "espera",
    "lista",
    "matrícula",
    "matricula",
    "máxima",
    "maxima",
    "mínima",
    "minima",
    "modalidade",
    "nota",
    "notas",
    "prazo",
    "resultado",
    "vagas",
    "cronograma",
}

def _is_sensitive(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in SENSITIVE_KEYWORDS)

def _extract_read_urls(messages: list) -> set[str]:
    called_urls = set()
    successful_urls = set()
    failed_urls = set()
    saw_fetch_result = False

    for m in messages:
        if isinstance(m, dict):
            tool_calls = m.get("tool_calls", [])
            content = m.get("content", "")
        else:
            tool_calls = getattr(m, "tool_calls", [])
            content = getattr(m, "content", "")

        for tc in tool_calls or []:
            if tc.get("name") == "web_csa_fetch":
                url = tc.get("args", {}).get("url")
                if url:
                    called_urls.add(url.strip())

        if not isinstance(content, str) or not content.lstrip().startswith("{"):
            continue

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict) or not payload.get("url"):
            continue

        saw_fetch_result = True
        url = str(payload["url"]).strip()
        if payload.get("error"):
            failed_urls.add(url)
            requested_url = payload.get("resolved_from_url")
            if requested_url:
                failed_urls.add(str(requested_url).strip())
        else:
            successful_urls.add(url)

    if successful_urls:
        return successful_urls
    if saw_fetch_result:
        return called_urls - failed_urls
    return called_urls


_CITED_URL_RE = re.compile(r"https?://[^\s)]+")
_LEADING_RESPONSE_LABEL_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?resposta\s*:(?:\*\*|__)?\s*",
    re.IGNORECASE,
)
_SOURCES_SECTION_RE = re.compile(
    r"\n\s*(?:#{1,6}\s*)?(?:\*\*|__)?fontes?\s*:(?:\*\*|__)?[\s\S]*$",
    re.IGNORECASE,
)
_INLINE_CITATION_RE = re.compile(r"\s*\[\d+\]")
_OFFICIAL_NOTICE_RE = re.compile(
    r"^\s*Em caso de divergência, prevalece o edital oficial\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CONVERSATIONAL_RE = re.compile(
    r"^(?:oi+|ol[aá]+|opa+|e\s+a[ií]|bom\s+dia|boa\s+tarde|boa\s+noite|"
    r"tudo\s+bem|como\s+vai|obrigad[oa]|valeu|beleza|entendi|tchau|at[eé]\s+mais)"
    r"[!,.?\s]*$",
    re.IGNORECASE,
)


def _is_conversational(text: str) -> bool:
    """Identifica mensagens sociais curtas que não exigem consulta a fontes."""
    return bool(_CONVERSATIONAL_RE.fullmatch(text.strip()))


def _has_source_lookup(messages: list) -> bool:
    """Informa se o agente realmente abriu uma fonte local ou remota."""
    has_fetch_call = False
    saw_fetch_result = False

    for message in messages:
        tool_calls = (
            message.get("tool_calls", [])
            if isinstance(message, dict)
            else getattr(message, "tool_calls", [])
        )
        for tool_call in tool_calls or []:
            name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            if name == "read":
                return True
            if name == "web_csa_fetch":
                has_fetch_call = True

        content = (
            message.get("content", "")
            if isinstance(message, dict)
            else getattr(message, "content", "")
        )
        if not isinstance(content, str) or not content.lstrip().startswith("{"):
            continue

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict) or not payload.get("url"):
            continue

        saw_fetch_result = True
        if not payload.get("error"):
            return True

    if has_fetch_call and not saw_fetch_result:
        return True

    return False


def _format_agent_response(response_text: str, *, source_was_consulted: bool) -> str:
    """Remove rótulos artificiais e citações sem uma fonte efetivamente consultada."""
    formatted = _LEADING_RESPONSE_LABEL_RE.sub("", response_text, count=1).strip()
    if source_was_consulted:
        return formatted

    formatted = _SOURCES_SECTION_RE.sub("", formatted)
    formatted = _OFFICIAL_NOTICE_RE.sub("", formatted)
    formatted = _INLINE_CITATION_RE.sub("", formatted)
    return formatted.strip()


def validate_agent_response(question: str, response_text: str, read_urls: set[str]) -> str | None:
    """Valida a resposta. Retorna uma mensagem de erro controlada se falhar, ou None se passar."""
    sensitive = _is_sensitive(question)
    has_fontes = "\nfontes:" in response_text.lower() or "\nfonte:" in response_text.lower()
    
    if sensitive and not has_fontes:
        return "Não consegui confirmar essa informação em uma fonte oficial válida neste momento. Tente novamente em instantes ou consulte o portal da CSA/UEFS: https://csa.uefs.br/."
    
    # Extrai as URLs citadas
    cited_urls = set(_CITED_URL_RE.findall(response_text))
    cleaned_cited = {u.rstrip(").,;'\"") for u in cited_urls}
    
    for url in cleaned_cited:
        if "csa.uefs.br" in url:
            base_url = url.split("#")[0]
            if not any(base_url in r.split("#")[0] for r in read_urls):
                # Hotfix protótipo: só bloqueia se for pergunta sensível; caso contrário permite (knowledge/ será refeito depois)
                if sensitive:
                    return "Não consegui validar uma das fontes citadas pelo agente. Para evitar informação incorreta, refaça a pergunta ou consulte o portal da CSA/UEFS: https://csa.uefs.br/."
    
    return None


def create_app(config_dir: str | Path | None = None) -> FastAPI:
    config_dir = Path(config_dir or os.getenv("AGENT_CONFIG_DIR") or ".ingester")

    app = FastAPI(
        title="Chat CSA — Agent API",
        version="0.1.0",
        description=(
            f"OpenAI-compatible chat completions backed by a LangChain tool agent "
            f"(config: {config_dir}). Compatible with OpenAI SDK and Ollama clients."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "config_dir": str(config_dir.resolve()),
            "config_exists": config_dir.exists(),
        }

    @app.get("/v1/models")
    async def list_models():
        # Publica um único nome de modelo derivado do config dir
        model_id = f"{config_dir.name or 'chat-csa'}-agent"
        return ModelsResponse(
            data=[
                ModelCard(id=model_id, created=int(time.time())),
                ModelCard(id="chat-csa", created=int(time.time())),
            ]
        )

    @app.get("/api/tags")
    async def ollama_tags():
        # Compat mínima com /api/tags do Ollama para ferramentas estilo `ollama list` não quebrarem
        model_id = f"{config_dir.name or 'chat-csa'}-agent"
        return {"models": [{"name": model_id, "model": model_id}]}

    @app.post("/v1/chat/completions")
    async def chat_completions(req: Request):
        body = await req.json()
        # Valida com folga; mantém compat com campos extras do SDK da OpenAI
        messages_raw = body.get("messages", [])
        messages = [ChatMessage(**m) if isinstance(m, dict) else m for m in messages_raw]
        stream = bool(body.get("stream", False))
        model = body.get("model", "chat-csa")
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        last_user_msg = _last_user_message_text(messages)

        cached = lookup_cached_answer(last_user_msg)
        if cached is not None:
            text = _format_agent_response(cached.to_markdown(), source_was_consulted=True)
            if not stream:
                return JSONResponse(
                    {
                        "id": completion_id,
                        "object": "chat.completion",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                        "chat_csa": {"cache": _cache_metadata(cached)},
                    }
                )

            async def cached_event_stream() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]})}\n\n"
                payload = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    "chat_csa": {"cache": _cache_metadata(cached)},
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(cached_event_stream(), media_type="text/event-stream")

        # Recarrega prompt + agente a cada request (barato; mantém hot-reload)
        system_prompt = build_system_prompt(Path(config_dir).resolve())
        agent, _, _, _ = build_agent(config_dir=config_dir)

        lc_messages = _openai_messages_to_lc(messages, system_prompt)

        force_buffer = _is_sensitive(last_user_msg) or _is_conversational(last_user_msg)

        if not stream or force_buffer:
            result = await agent.ainvoke({"messages": lc_messages})
            result_messages = result.get("messages", [])
            text = _format_agent_response(
                _extract_text_from_agent_result(result),
                source_was_consulted=_has_source_lookup(result_messages),
            )
            
            read_urls = _extract_read_urls(result_messages)
            err = validate_agent_response(last_user_msg, text, read_urls)
            if err:
                text = err

            if not stream:
                return JSONResponse(
                    {
                        "id": completion_id,
                        "object": "chat.completion",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    }
                )
            
            # Streaming simulado após buffer (para consultas críticas)
            async def fake_event_stream() -> AsyncIterator[str]:
                yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]})}\n\n"
                payload = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
                
            return StreamingResponse(fake_event_stream(), media_type="text/event-stream")

        # Streaming real (apenas para consultas não-críticas, pois validação exige texto final completo)
        async def event_stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]})}\n\n"
            try:
                async for chunk in agent.astream({"messages": lc_messages}, stream_mode="messages"):
                    msg_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
                    text = getattr(msg_chunk, "content", "")
                    if isinstance(text, list):
                        flat = ""
                        for part in text:
                            if isinstance(part, dict) and "text" in part:
                                flat += part["text"]
                            elif isinstance(part, str):
                                flat += part
                        text = flat
                    text = str(text) if text else ""
                    if not text:
                        continue
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                err = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(err)}\n\n"
            yield f"data: {json.dumps({'id': completion_id,'object':'chat.completion.chunk','created':created,'model':model,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # Compatibilidade nativa com o Ollama: POST /api/chat
    # ------------------------------------------------------------------
    @app.post("/api/chat")
    async def ollama_chat(req: Request):
        """Shim mínimo de /api/chat do Ollama que repassa a chamada ao mesmo agente.
        Aceita {model, messages, stream} do Ollama e devolve saída no formato dele.
        """
        body = await req.json()
        messages_raw = body.get("messages", [])
        stream = bool(body.get("stream", False))
        model = body.get("model", "chat-csa")

        # Mensagens do Ollama são {role, content}
        messages = []
        for m in messages_raw:
            messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))

        last_user_msg = _last_user_message_text(messages)
        cached = lookup_cached_answer(last_user_msg)
        if cached is not None:
            text = _format_agent_response(cached.to_markdown(), source_was_consulted=True)
            if not stream:
                return JSONResponse(
                    {
                        "model": model,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "message": {"role": "assistant", "content": text},
                        "done": True,
                        "chat_csa_cache": _cache_metadata(cached),
                    }
                )

            async def cached_ollama_stream() -> AsyncIterator[str]:
                yield json.dumps(
                    {
                        "model": model,
                        "message": {"role": "assistant", "content": text},
                        "done": False,
                        "chat_csa_cache": _cache_metadata(cached),
                    },
                    ensure_ascii=False,
                ) + "\n"
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

            return StreamingResponse(cached_ollama_stream(), media_type="application/x-ndjson")

        system_prompt = build_system_prompt(Path(config_dir).resolve())
        agent, _, _, _ = build_agent(config_dir=config_dir)
        lc_messages = _openai_messages_to_lc(messages, system_prompt)

        force_buffer = _is_sensitive(last_user_msg) or _is_conversational(last_user_msg)

        if not stream or force_buffer:
            result = await agent.ainvoke({"messages": lc_messages})
            result_messages = result.get("messages", [])
            text = _format_agent_response(
                _extract_text_from_agent_result(result),
                source_was_consulted=_has_source_lookup(result_messages),
            )
            
            read_urls = _extract_read_urls(result_messages)
            err = validate_agent_response(last_user_msg, text, read_urls)
            if err:
                text = err

            if not stream:
                return JSONResponse(
                    {
                        "model": model,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "message": {"role": "assistant", "content": text},
                        "done": True,
                    }
                )
            
            # Streaming falso para Ollama
            async def fake_ollama_stream() -> AsyncIterator[str]:
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": text}, "done": False}) + "\n"
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

            return StreamingResponse(fake_ollama_stream(), media_type="application/x-ndjson")

        async def ollama_stream() -> AsyncIterator[str]:
            async for chunk in agent.astream({"messages": lc_messages}, stream_mode="messages"):
                msg_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
                text = getattr(msg_chunk, "content", "")
                if isinstance(text, list):
                    flat = ""
                    for part in text:
                        if isinstance(part, dict) and "text" in part:
                            flat += part["text"]
                        elif isinstance(part, str):
                            flat += part
                    text = flat
                text = str(text) if text else ""
                if not text:
                    continue
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": text}, "done": False}) + "\n"
            yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

        return StreamingResponse(ollama_stream(), media_type="application/x-ndjson")

    # ------------------------------------------------------------------
    # Auth — login do ingester + CRUD admin simples (admin / sudo123)
    # ------------------------------------------------------------------
    @app.post("/auth/login")
    async def auth_login_route(req: Request):
        body = await req.json()
        username = body.get("username", "")
        password = body.get("password", "")
        return auth_store.login(username=username, password=password)

    @app.get("/auth/me")
    async def auth_me(authorization: str | None = Header(default=None)):
        user = auth_store.verify_token(authorization)
        if not user:
            return JSONResponse({"authenticated": False}, status_code=401)
        return {"authenticated": True, "user": user}

    def _require_admin(authorization: str | None = Header(default=None)):
        return auth_store.require_auth(authorization)

    @app.get("/admin/users")
    async def admin_list(authorization: str | None = Header(default=None)):
        _require_admin(authorization)
        return auth_store.list_users()

    @app.post("/admin/users")
    async def admin_create(req: Request, authorization: str | None = Header(default=None)):
        _require_admin(authorization)
        body = await req.json()
        return auth_store.create_user(
            username=body.get("username", ""),
            password=body.get("password", ""),
            role=body.get("role", "admin"),
        )

    @app.put("/admin/users/{uid}")
    async def admin_update(uid: str, req: Request, authorization: str | None = Header(default=None)):
        _require_admin(authorization)
        body = await req.json()
        return auth_store.update_user(uid, username=body.get("username"), password=body.get("password"), role=body.get("role"))

    @app.delete("/admin/users/{uid}")
    async def admin_delete(uid: str, authorization: str | None = Header(default=None)):
        _require_admin(authorization)
        return auth_store.delete_user(uid)

    return app


# App padrão para `uvicorn chat_csa.server.app:app`
# Usa a env AGENT_CONFIG_DIR (padrão: .ingester)
app = create_app()
