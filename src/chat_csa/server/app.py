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
from ..qa_cache import format_faq_reference, lookup_cached_matches
from . import auth as auth_store
from .admin import build_admin_panel
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


def _faq_reference_block(question: str) -> str:
    """Monta o bloco de FAQ curada injetado no system prompt quando há entradas relevantes.

    A FAQ não responde diretamente: entra como referência curada para o agente
    formular a resposta no turno, adaptada ao contexto da conversa.
    """
    hits = lookup_cached_matches(question)
    if not hits:
        return ""
    lines = [
        "## FAQ curada (referências recuperadas para a pergunta do usuário)",
        "",
        "Use essas respostas como referência primária quando aplicáveis, adaptando-as ao contexto da conversa e citando as fontes. "
        "Entradas que avisam que a informação pode mudar exigem conferência nas fontes oficiais antes de afirmar datas, prazos ou situação atual. "
        "Se a pergunta envolver situação individual, cotas, documentos ou datas críticas, confirme nas fontes oficiais mesmo quando a FAQ cobrir o tema.",
    ]
    for hit in hits:
        lines.append("")
        lines.append(format_faq_reference(hit.entry))
    return "\n".join(lines)


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


def _openai_chunk(completion_id: str, created: int, model: str, delta: dict, finish_reason=None) -> str:
    """Monta um chunk SSE no formato OpenAI; delta pode carregar campos
    extras (reasoning/tool_call) que clientes externos ignoram."""
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _reasoning_from_message(message) -> str:
    """Extrai reasoning (thinking) de uma mensagem ou chunk do LangChain.

    O langchain-ollama mapeia o campo `thinking` do Ollama para
    additional_kwargs['reasoning_content'] (invoke e stream).
    """
    if isinstance(message, dict):
        additional = message.get("additional_kwargs", {}) or {}
    else:
        additional = getattr(message, "additional_kwargs", {}) or {}
    reasoning = additional.get("reasoning_content") or additional.get("reasoning") or ""
    if isinstance(reasoning, list):
        parts = []
        for part in reasoning:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(reasoning)


def _tool_call_parts(tool_call) -> tuple[str, str, dict]:
    """Normaliza uma tool call (dict ou objeto) para (id, name, args)."""
    if isinstance(tool_call, dict):
        tid = tool_call.get("id") or ""
        name = tool_call.get("name") or tool_call.get("function", {}).get("name") or ""
        raw_args = tool_call.get("args")
        if raw_args is None:
            raw_args = tool_call.get("function", {}).get("arguments", {})
    else:
        tid = getattr(tool_call, "id", "") or ""
        name = getattr(tool_call, "name", "") or ""
        raw_args = getattr(tool_call, "args", {})
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError:
            raw_args = {"raw": raw_args}
    if not isinstance(raw_args, dict):
        raw_args = {"value": str(raw_args)}
    return tid, name, raw_args


def _tool_result_is_error(content) -> bool:
    """Heurística simples: resultado de ferramenta começou com erro."""
    text = str(content).lstrip().lower()
    return text.startswith("error") or '"error"' in text[:500]


def _tool_events_from_messages(messages: list) -> list[dict]:
    """Converte a lista de mensagens do agente em eventos de ferramenta
    ordenados: {type: tool_start, id, name, args} seguido de
    {type: tool_end, id, name, error} por chamada."""
    events: list[dict] = []
    open_calls: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls") or []
            msg_type = message.get("type") or message.get("role")
            tool_call_id = message.get("tool_call_id")
            content = message.get("content", "")
        else:
            tool_calls = getattr(message, "tool_calls", None) or []
            msg_type = getattr(message, "type", None)
            tool_call_id = getattr(message, "tool_call_id", None)
            content = getattr(message, "content", "")
        for tool_call in tool_calls:
            tid, name, args = _tool_call_parts(tool_call)
            if not name:
                continue
            event = {"type": "tool_start", "id": tid, "name": name, "args": args}
            events.append(event)
            open_calls[tid] = event
        if msg_type == "tool" and tool_call_id in open_calls:
            start = open_calls.pop(tool_call_id)
            events.append(
                {
                    "type": "tool_end",
                    "id": tool_call_id,
                    "name": start["name"],
                    "error": _tool_result_is_error(content),
                }
            )
    return events


def _trace_from_messages(messages: list) -> tuple[str, list[dict]]:
    """Caminho bufferizado: (reasoning completo, eventos de ferramenta)."""
    reasoning_parts = [r for r in (_reasoning_from_message(m) for m in messages) if r]
    return "\n".join(reasoning_parts), _tool_events_from_messages(messages)


_LEADING_RESPONSE_LABEL_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?resposta\s*:(?:\*\*|__)?\s*",
    re.IGNORECASE,
)
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
    """Higieniza o formato da resposta sem bloquear (guia > bloqueio).

    Remove rótulos artificiais e a nota de divergência órfã quando nenhuma
    fonte foi consultada. Nunca apaga a seção Fontes nem as citações: o
    agente é guiado pelo prompt a citar corretamente, não punido depois.
    """
    formatted = _LEADING_RESPONSE_LABEL_RE.sub("", response_text, count=1).strip()
    if not source_was_consulted:
        formatted = _OFFICIAL_NOTICE_RE.sub("", formatted)
    return formatted.strip()


_RESPONSE_GUIDE_BLOCK = """## Guia de citações (obrigatório)

- Termine a resposta com uma seção `Fontes:` sempre que usar qualquer fonte: FAQ curada, arquivos de knowledge/ ou páginas do portal.
- Formato de cada fonte: `[1] Nome da fonte — URL`; para FAQ curada injetada use `[1] FAQ curada — cache FAQ-XXX`.
- Cite a fonte inline com `[N]` logo após a informação que veio dela.
- Fontes válidas: a FAQ curada injetada neste prompt, arquivos lidos com `read` e páginas abertas com `web_csa_fetch` no turno.
- Não invente URLs: se não abriu a página no turno, cite a FAQ curada ou o arquivo knowledge/ que usou.
"""


def _prompt_extra(faq_block: str) -> str:
    """Junta o bloco de FAQ recuperada com o guia de citações para o system prompt."""
    blocks = [b for b in (faq_block, _RESPONSE_GUIDE_BLOCK.strip()) if b]
    return "\n\n".join(blocks)


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

        # Recarrega prompt + agente a cada request (barato; mantém hot-reload).
        # FAQ curada: injeta entradas relevantes como referência no prompt —
        # a resposta é formulada pelo agente no turno, sem short-circuit.
        faq_block = _faq_reference_block(last_user_msg)
        system_prompt = build_system_prompt(
            Path(config_dir).resolve(), extra=_prompt_extra(faq_block)
        )
        agent, _, _, _ = build_agent(config_dir=config_dir)

        lc_messages = _openai_messages_to_lc(messages, system_prompt)

        force_buffer = _is_conversational(last_user_msg)

        if not stream or force_buffer:
            result = await agent.ainvoke({"messages": lc_messages})
            result_messages = result.get("messages", [])
            text = _format_agent_response(
                _extract_text_from_agent_result(result),
                source_was_consulted=_has_source_lookup(result_messages) or bool(faq_block),
            )
            # Rastro da atividade do agente (caminho bufferizado): reasoning
            # completo + eventos de ferramenta, reemitidos no JSON/SSE.
            reasoning_text, tool_events = _trace_from_messages(result_messages)

            if not stream:
                return JSONResponse(
                    {
                        "id": completion_id,
                        "object": "chat.completion",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": text,
                                    # Campos extras (fora do spec OpenAI):
                                    # consumidos pelo frontend do Chat CSA.
                                    "reasoning": reasoning_text,
                                    "tool_steps": tool_events,
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    }
                )

            # Streaming simulado após buffer (para consultas críticas): emite
            # o rastro completo de uma vez, no mesmo formato do stream real.
            async def fake_event_stream() -> AsyncIterator[str]:
                yield _openai_chunk(completion_id, created, model, {"role": "assistant"})
                if reasoning_text:
                    yield _openai_chunk(completion_id, created, model, {"reasoning": reasoning_text})
                for event in tool_events:
                    yield _openai_chunk(completion_id, created, model, {"tool_call": event})
                yield _openai_chunk(completion_id, created, model, {"content": text})
                yield _openai_chunk(completion_id, created, model, {}, finish_reason="stop")
                yield "data: [DONE]\n\n"

            return StreamingResponse(fake_event_stream(), media_type="text/event-stream")

        # Streaming real: emite thinking (delta.reasoning), passos de ferramenta
        # (delta.tool_call) e tokens da resposta (delta.content) ao vivo.
        async def event_stream() -> AsyncIterator[str]:
            yield _openai_chunk(completion_id, created, model, {"role": "assistant"})
            streamed_messages: list = []
            seen_events = 0
            try:
                async for mode, data in agent.astream(
                    {"messages": lc_messages}, stream_mode=["updates", "messages"]
                ):
                    if mode == "messages":
                        msg_chunk = data[0] if isinstance(data, tuple) else data
                        # Chunks do grafo com metadados: resultados de ferramentas
                        # streamados (langgraph_node == "tools") não são resposta
                        # final — só reemite conteúdo gerado pelo modelo.
                        meta = data[1] if isinstance(data, tuple) and len(data) > 1 else {}
                        if meta.get("langgraph_node") == "tools":
                            continue
                        reasoning = _reasoning_from_message(msg_chunk)
                        if reasoning:
                            yield _openai_chunk(completion_id, created, model, {"reasoning": reasoning})
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
                        yield _openai_chunk(completion_id, created, model, {"content": text})
                        continue

                    # mode == "updates": mensagens novas por passo do agente
                    if isinstance(data, dict):
                        for payload in data.values():
                            msgs = payload.get("messages", []) if isinstance(payload, dict) else []
                            streamed_messages.extend(msgs)
                    events = _tool_events_from_messages(streamed_messages)
                    for event in events[seen_events:]:
                        yield _openai_chunk(completion_id, created, model, {"tool_call": event})
                    seen_events = len(events)
            except Exception as e:
                err = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(err)}\n\n"
            yield _openai_chunk(completion_id, created, model, {}, finish_reason="stop")
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

        # FAQ curada: injeta entradas relevantes como referência no prompt —
        # a resposta é formulada pelo agente no turno, sem short-circuit.
        faq_block = _faq_reference_block(last_user_msg)
        system_prompt = build_system_prompt(
            Path(config_dir).resolve(), extra=_prompt_extra(faq_block)
        )
        agent, _, _, _ = build_agent(config_dir=config_dir)
        lc_messages = _openai_messages_to_lc(messages, system_prompt)

        force_buffer = _is_conversational(last_user_msg)

        if not stream or force_buffer:
            result = await agent.ainvoke({"messages": lc_messages})
            result_messages = result.get("messages", [])
            text = _format_agent_response(
                _extract_text_from_agent_result(result),
                source_was_consulted=_has_source_lookup(result_messages) or bool(faq_block),
            )
            # Rastro da atividade do agente (caminho bufferizado).
            reasoning_text, tool_events = _trace_from_messages(result_messages)

            if not stream:
                return JSONResponse(
                    {
                        "model": model,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "message": {
                            "role": "assistant",
                            "content": text,
                            # Campos extras: consumidos pelo frontend do Chat CSA.
                            "reasoning": reasoning_text,
                            "tool_steps": tool_events,
                        },
                        "done": True,
                    }
                )

            # Streaming falso para Ollama: emite reasoning/steps antes do texto.
            async def fake_ollama_stream() -> AsyncIterator[str]:
                if reasoning_text:
                    yield json.dumps(
                        {"model": model, "message": {"role": "assistant", "reasoning": reasoning_text, "content": ""}, "done": False}
                    ) + "\n"
                for event in tool_events:
                    yield json.dumps(
                        {"model": model, "message": {"role": "assistant", "tool_call": event, "content": ""}, "done": False}
                    ) + "\n"
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": text}, "done": False}) + "\n"
                yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

            return StreamingResponse(fake_ollama_stream(), media_type="application/x-ndjson")

        async def ollama_stream() -> AsyncIterator[str]:
            streamed_messages: list = []
            seen_events = 0
            async for mode, data in agent.astream(
                {"messages": lc_messages}, stream_mode=["updates", "messages"]
            ):
                if mode == "messages":
                    msg_chunk = data[0] if isinstance(data, tuple) else data
                    # Ignora resultados de ferramenta streamados pelo grafo
                    # (langgraph_node == "tools") — não são a resposta final.
                    meta = data[1] if isinstance(data, tuple) and len(data) > 1 else {}
                    if meta.get("langgraph_node") == "tools":
                        continue
                    reasoning = _reasoning_from_message(msg_chunk)
                    if reasoning:
                        yield json.dumps(
                            {"model": model, "message": {"role": "assistant", "reasoning": reasoning, "content": ""}, "done": False}
                        ) + "\n"
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
                    continue

                # mode == "updates": passos de ferramenta (nome + args + resultado)
                if isinstance(data, dict):
                    for payload in data.values():
                        msgs = payload.get("messages", []) if isinstance(payload, dict) else []
                        streamed_messages.extend(msgs)
                events = _tool_events_from_messages(streamed_messages)
                for event in events[seen_events:]:
                    yield json.dumps(
                        {"model": model, "message": {"role": "assistant", "tool_call": event, "content": ""}, "done": False}
                    ) + "\n"
                seen_events = len(events)
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

    # Painel FastHTML do ingester (decisão da discussão ingester-fasthtml-admin):
    # o admin só existe no servidor do ingester; o consumer permanece API pura.
    # Montado após as rotas JSON /admin/users para não sobrescrevê-las (o match
    # exato de rota tem precedência sobre o prefixo do mount).
    if config_dir.name.startswith(".ingester"):
        app.mount("/admin", build_admin_panel(), name="admin")

    return app


# App padrão para `uvicorn chat_csa.server.app:app`
# Usa a env AGENT_CONFIG_DIR (padrão: .ingester)
app = create_app()
