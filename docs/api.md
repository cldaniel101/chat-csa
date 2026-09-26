# API HTTP

Este documento descreve a API HTTP dos agentes: rotas compatíveis com OpenAI e com Ollama, o formato de streaming (incluindo os campos extras do Chat CSA) e as rotas de autenticação e administração do ingester. O público são integradores que vão consumir a API de outra aplicação.

## Endpoints

O mesmo app FastAPI é servido por qualquer agente; o que muda é o config dir e a porta (padrão: ingester em `:8001`, consumer em `:8002`). Todas as rotas nascem de `create_app` em `src/chat_csa/server/app.py`.

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| GET | `/health` | — | status do processo + caminho do config dir |
| GET | `/v1/models` | — | lista de modelos (nome derivado do config dir + `chat-csa`) |
| GET | `/api/tags` | — | compat mínima com o `ollama list` |
| POST | `/v1/chat/completions` | — | chat compatível com OpenAI (stream e non-stream) |
| POST | `/api/chat` | — | shim compatível com Ollama (stream e non-stream) |
| POST | `/auth/login` | — | login do ingester; devolve `access_token` |
| GET | `/auth/me` | `Authorization` (Bearer) | valida o token e devolve o usuário |
| GET | `/admin/users` | `Authorization` (Bearer) | lista usuários (sem senha) |
| POST | `/admin/users` | `Authorization` (Bearer) | cria usuário |
| PUT | `/admin/users/{uid}` | `Authorization` (Bearer) | atualiza usuário |
| DELETE | `/admin/users/{uid}` | `Authorization` (Bearer) | remove usuário (não permite remover o último) |
| GET | `/admin` | cookie de sessão | painel FastHTML do ingester: login ou chat |
| POST | `/admin/login` | — | valida credenciais e abre a sessão por cookie |
| POST | `/admin/logout` | cookie de sessão | encerra a sessão |

O mount `/admin` só existe no processo cujo config dir começa com `.ingester`; no consumer a rota responde 404. O painel HTML é montado **depois** das rotas JSON `/admin/users`, então o CRUD continua acessível por Bearer.

> Nota: o docstring do módulo cita um `POST /v1/completions` "não implementado — retorna 501". Não há rota registrada para esse caminho; uma chamada cai no 404 padrão do FastAPI. O endpoint existe apenas como intenção documentada.

## Chat completions (OpenAI)

Corpo aceito (`src/chat_csa/server/models.py`): `model`, `messages` (lista de `{role, content}`, com `tool_calls` opcionais em mensagens de assistente), `stream`, `temperature`, `max_tokens`, `top_p`, `n`, `stop`, `tools`, `tool_choice` e campos extras liberados (`"extra": "allow"`). O servidor **não** usa os parâmetros de amostragem: quem controla isso é a fábrica do LLM.

Sem streaming (`"stream": false`), a resposta é um JSON no formato OpenAI com dois campos extras fora do spec, consumidos pelo frontend:

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "...",
      "reasoning": "raciocínio do modelo (thinking)",
      "tool_steps": [{ "type": "tool_start", "id": "...", "name": "web_csa_fetch", "args": {} }]
    }
  }]
}
```

Com streaming, a resposta é `text/event-stream` no formato OpenAI SSE. Cada chunk traz `choices[0].delta`; além de `content`, o Chat CSA emite deltas com `reasoning` (thinking) e `tool_call` (eventos `tool_start`/`tool_end`). A sequência termina com `finish_reason: "stop"` e a linha `data: [DONE]`.

Mensagens sociais curtas ("oi", "obrigado") são detectadas por `_is_conversational` e respondidas em modo bufferizado mesmo com `stream: true` (o cliente recebe o stream simulado, sem consulta a fontes). Erros durante o stream são emitidos como um chunk `{"error": {"message": "...", "type": "server_error"}}`.

## Shim do Ollama

`POST /api/chat` aceita `{model, messages, stream}` e devolve o formato do Ollama: sem stream, um JSON com `message.role`, `message.content`, `done: true` (e os extras `reasoning`/`tool_steps`); com stream, NDJSON com uma linha por evento e `done: true` na última. `GET /api/tags` devolve o modelo derivado do config dir para ferramentas que listam modelos.

## Autenticação e administração

`POST /auth/login` recebe `{username, password}` e devolve `{access_token, token_type: "bearer", user}`. As rotas `/auth/me` e `/admin/users` aceitam `Authorization: Bearer <token>` ou o token puro (`verify_token`). O store é **em memória** (`src/chat_csa/server/auth.py`): reiniciar o processo derruba usuários e tokens.

O painel `/admin` troca o Bearer por um cookie de sessão `csa_admin_token` (`HttpOnly`, `SameSite=Lax`, `path=/admin`; `Secure` quando `ADMIN_COOKIE_SECURE=1`). Ele é uma superfície do ingester apenas; o consumer permanece API pura.

## Exemplos de consumo

`examples/curl.md` traz os quatro curls básicos (OpenAI stream/non-stream e Ollama stream/non-stream); `examples/openai_client.py` usa o SDK da OpenAI com `base_url="http://localhost:8001/v1"` e `api_key` fictícia; `examples/ollama_client.py` usa `httpx` contra `/api/chat`.

```bash
# non-stream
curl http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"quais documentos para matrícula?"}]}'

# stream
curl -N http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"explique a lista de espera"}],"stream":true}'
```

## Fontes

- `src/chat_csa/server/app.py`
- `src/chat_csa/server/models.py`
- `src/chat_csa/server/auth.py`
- `src/chat_csa/server/admin.py`
- `api/index.py`
- `examples/curl.md`, `examples/openai_client.py`, `examples/ollama_client.py`
- `frontend/src/api/client.ts` (o que o cliente do widget consome)
