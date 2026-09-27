# API HTTP

Este documento descreve a API HTTP do agente **consumer**: rotas compatíveis com OpenAI e com Ollama, o formato de streaming (incluindo os campos extras do Chat CSA) e a superfície admin `/kb/*` da base de conhecimento remota. O público são integradores que vão consumir a API de outra aplicação.

## Endpoints

Há um único agente (consumer) e um único app FastAPI, criado por `create_app` em `src/chat_csa/server/app.py`. Em dev, ele roda em `:8002`.

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| GET | `/health` | — | status do processo + caminho do config dir |
| GET | `/v1/models` | — | lista de modelos (nome derivado do config dir + `chat-csa`) |
| GET | `/api/tags` | — | compat mínima com o `ollama list` |
| POST | `/v1/chat/completions` | — | chat compatível com OpenAI (stream e non-stream) |
| POST | `/api/chat` | — | shim compatível com Ollama (stream e non-stream) |
| POST | `/auth/login` | — | login admin; devolve `access_token` |
| GET | `/auth/me` | `Authorization` (Bearer) | valida o token e devolve o usuário |
| GET | `/admin/users` | `Authorization` (Bearer) | lista usuários (sem senha) |
| POST | `/admin/users` | `Authorization` (Bearer) | cria usuário |
| PUT | `/admin/users/{uid}` | `Authorization` (Bearer) | atualiza usuário |
| DELETE | `/admin/users/{uid}` | `Authorization` (Bearer) | remove usuário (não permite remover o último) |
| GET | `/kb/list?prefix=` | `Authorization` (Bearer admin) | caminhos disponíveis na base |
| GET | `/kb/file?path=` | `Authorization` (Bearer admin) | bytes originais do arquivo, com content-type |
| POST | `/kb/upload` | `Authorization` (Bearer admin) | converte o lote em conceitos OKF → um commit atômico no branch `data` |

O agente **não** passa por `/kb/*`: ele fala com o cliente `chat_csa.kb` em processo (`kb_list`/`kb_read`, token de leitura) e nunca recebe credencial de admin.

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
      "tool_steps": [{ "type": "tool_start", "id": "...", "name": "kb_read", "args": {} }]
    }
  }]
}
```

Com streaming, a resposta é `text/event-stream` no formato OpenAI SSE. Cada chunk traz `choices[0].delta`; além de `content`, o Chat CSA emite deltas com `reasoning` (thinking) e `tool_call` (eventos `tool_start`/`tool_end`). A sequência termina com `finish_reason: "stop"` e a linha `data: [DONE]`.

Mensagens sociais curtas ("oi", "obrigado") são detectadas por `_is_conversational` e respondidas em modo bufferizado mesmo com `stream: true` (o cliente recebe o stream simulado, sem consulta a fontes). Erros durante o stream são emitidos como um chunk `{"error": {"message": "...", "type": "server_error"}}`.

## Shim do Ollama

`POST /api/chat` aceita `{model, messages, stream}` e devolve o formato do Ollama: sem stream, um JSON com `message.role`, `message.content`, `done: true` (e os extras `reasoning`/`tool_steps`); com stream, NDJSON com uma linha por evento e `done: true` na última. `GET /api/tags` devolve o modelo derivado do config dir para ferramentas que listam modelos.

## Autenticação e administração

`POST /auth/login` recebe `{username, password}` e devolve `{access_token, token_type: "bearer", user}`. As rotas `/auth/me`, `/admin/users` e `/kb/*` aceitam `Authorization: Bearer <token>` ou o token puro (`verify_token`). O store é **em memória** (`src/chat_csa/server/auth.py`): reiniciar o processo derruba usuários e tokens.

A auth admin protege duas superfícies: o CRUD de usuários (`/admin/users`) e o upload/inspeção da base (`/kb/*`). O antigo painel FastHTML `/admin` foi removido junto com o agente ingester.

## Base de conhecimento (`/kb/*`)

A base vive no branch órfão `data` do próprio repositório e é lida em runtime pela API do GitHub. As rotas são a superfície **admin** (o time envia conteúdo por elas); o agente consome a base em processo, sem HTTP.

### `GET /kb/list?prefix=`

Devolve os caminhos disponíveis na base, relativos à raiz (`KB_ROOT`), opcionalmente filtrados por prefixo:

```json
{ "prefix": "perguntas-frequentes", "paths": ["perguntas-frequentes/faq-cotas.md", "..."] }
```

### `GET /kb/file?path=`

Devolve os **bytes originais** do arquivo com o content-type adequado. A conversão por tipo (csv → tabela, pdf → texto, binário → aviso) acontece na leitura do agente (`kb_read`), nunca aqui e nunca é gravada no branch. Conceitos enviados pelo `/kb/upload` novo não têm original na base — só o `.md` convertido.

### `POST /kb/upload`

Multipart em lote: o caminho declarado de cada arquivo vem no **filename** da parte e vira o conceito `<pasta>/<slug>.md` (o servidor normaliza caracteres e troca a extensão). Cada arquivo é **convertido dentro do request** — o original não é preservado — e conceitos + índices vão num **único commit atômico** no branch `data` (Git Data API); nunca existe lote parcial.

Tipos convertidos: `pdf` (texto extraído por layout + imagens das páginas numa chamada multimodal, lote a lote), imagens, `csv`/`tsv` (tabela Markdown) e `md`/`txt`/`json` (texto direto). Demais tipos (docx/xlsx/html…) ficam para depois: o arquivo não é gravado e a resposta marca `converted: false`.

O `sources` (opcional) é um JSON `{"caminho declarado": "URL da fonte"}`; com ele o conceito ganha `resource`/`url`/`source_page` e a seção `# Citations`; sem ele, nada de citação é inventado. Conceito existente no mesmo caminho é sobrescrito (o git guarda o histórico) e o bullet do índice é atualizado no mesmo commit; seção nova cria a pasta e o índice no mesmo commit.

```bash
TOKEN=$(curl -s http://localhost:8002/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<senha>"}' | jq -r .access_token)

curl -s http://localhost:8002/kb/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F 'files=@./faq-cotas.md;filename=perguntas-frequentes/faq-cotas.md' \
  -F 'files=@./cronograma.pdf;filename=cronogramas/cronograma.pdf' \
  -F 'sources={"cronogramas/cronograma.pdf": "https://csa.uefs.br/cronograma.pdf"}' \
  -F 'message=kb: primeiro lote do time'
```

Resposta de sucesso (por arquivo + sha do commit; aditiva, **sem eco do Markdown**):

```json
{
  "ok": true,
  "sha": "e062755...",
  "files": [
    { "path": "perguntas-frequentes/faq-cotas.md", "ok": true, "size": 2662, "converted": true },
    { "path": "cronogramas/cronograma.pdf", "ok": true, "size": 81234, "converted": true }
  ]
}
```

Um arquivo que não converte **não aborta o lote**: ele não entra na base e a resposta traz `"converted": false` com o motivo em `error` (tipo sem conversão, falha do modelo, arquivo acima do orçamento). Caminho inválido ou duplicado vem com `"ok": false` e nenhum arquivo inválido entra no commit.

Em falha de infraestrutura (ex.: token de escrita ausente, branch inexistente), a resposta traz `ok: false`, o erro e cada arquivo marcado como `ok: false`; nada é commitado. O teto de corpo da Vercel (~4.5 MB) limita o lote — lotes maiores devem ser fatiados pelo cliente.

## Exemplos de consumo

`examples/curl.md` traz os quatro curls básicos (OpenAI stream/non-stream e Ollama stream/non-stream); `examples/openai_client.py` usa o SDK da OpenAI com `base_url="http://localhost:8002/v1"` e `api_key` fictícia; `examples/ollama_client.py` usa `httpx` contra `/api/chat`.

```bash
# non-stream
curl http://localhost:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"quais documentos para matrícula?"}]}'

# stream
curl -N http://localhost:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"explique a lista de espera"}],"stream":true}'
```

## Fontes

- `src/chat_csa/server/app.py`
- `src/chat_csa/server/models.py`
- `src/chat_csa/server/auth.py`
- `src/chat_csa/server/kb_api.py`
- `src/chat_csa/kb.py`
- `api/index.py`
- `examples/curl.md`, `examples/openai_client.py`, `examples/ollama_client.py`
- `frontend/src/api/client.ts` (o que o cliente do widget consome)
