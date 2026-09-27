# Configuração

Este documento é a referência de configuração do Chat CSA para quem opera o sistema: variáveis de ambiente do backend e do frontend, defaults de `pyproject.toml`, o que o `docker-compose.yml` e o `Dockerfile` fixam e como as precedências funcionam. Ele não repete o passo a passo de desenvolvimento — isso está em [desenvolvimento.md](./desenvolvimento.md).

## Variáveis de ambiente do backend

Fonte principal: `.env.example` (copie para `.env`). Variáveis que aparecem apenas no código estão marcadas com o arquivo que as lê.

| Variável | Para que serve | Default / origem |
|---|---|---|
| `LLM_PROVIDER` | provedor: `ollama`, `openai` ou `fake` | `ollama` (`agent/factory.py`) |
| `LLM_MODEL` | modelo (fallback `MODEL`) | — |
| `OLLAMA_MODEL` | modelo do Ollama quando `LLM_MODEL` não cobre | `gemma4:31b-cloud` (`factory.py`) |
| `OLLAMA_BASE_URL` | endpoint do Ollama | `http://localhost:11434` |
| `OLLAMA_API_KEY` | token do Ollama Cloud; vira header Bearer | vazio |
| `OLLAMA_REASONING` | liga/desliga o campo `reasoning` (`0/false/no/off` desliga) | `1` (`factory.py`) |
| `OPENAI_API_KEY` | chave OpenAI-compatible | — |
| `OPENAI_MODEL` | modelo OpenAI quando `LLM_MODEL` não cobre | `gpt-4o-mini` (`factory.py`) |
| `OPENAI_BASE_URL` | base para Azure/OpenRouter/proxies | vazio |
| `AGENT_CONFIG_DIR` | config dir do agente | `.consumer` (`app.py`, `cli.py`, `api/index.py`) |
| `HOST` / `PORT` | bind do `chat-csa serve` | `0.0.0.0` / `8000` (`cli.py`) |
| `CONSUMER_CONFIG_DIR` / `CONSUMER_PORT` | dir e porta do consumer | `.consumer` / `8002` (Makefile) |
| `CONSUMER_LLM_*` / `CONSUMER_HOST` | override de provedor/modelo/chave/bind | comentados no `.env.example` |
| `KB_BACKEND` | backend da base: `github` (deploy) ou `local` (dev/testes) | `github` (`kb.py`) |
| `KB_REPO` | repositório `owner/name` que guarda o branch da base | — (`kb.py`) |
| `KB_BRANCH` | branch da base | `data` (`kb.py`) |
| `KB_ROOT` | prefixo do bundle dentro do branch | vazio (raiz) (`kb.py`) |
| `KB_TOKEN` | token de leitura (fine-grained, `contents:read`) | vazio (`kb.py`) |
| `KB_WRITE_TOKEN` | token de escrita para `/kb/upload`; fallback `KB_TOKEN` | vazio (`kb.py`) |
| `KB_CACHE_TTL` | TTL do cache em memória, em segundos (`0` desliga) | `60` (`kb.py`) |
| `KB_LOCAL_PATH` | diretório da base no backend local | `knowledge` (`kb.py`) |
| `KB_CONVERT_MODEL` | modelo multimodal da conversão do `/kb/upload` (vazio = `LLM_MODEL`) | vazio (`kb_convert.py`) |
| `KB_CONVERT_PAGES_PER_CALL` | páginas de PDF por chamada multimodal no upload | `4` (`kb_convert.py`) |
| `KB_UPLOAD_MAX_BYTES` | orçamento de bytes por arquivo no upload (teto do corpo da Vercel ~4.5 MB) | `4500000` (`kb_upload.py`) |
| `CHAT_CSA_PORTAL_TOOLS` | `1` liga `web_csa_fetch`/`web_csa_search` no agente | `0` (`factory.py`) |
| `CHAT_CSA_QA_CACHE_ENABLED` | liga/desliga a injeção da FAQ curada | `1` (`qa_cache.py`) |
| `CHAT_CSA_QA_CACHE_PATHS` | prefixos da FAQ na base, separados por `os.pathsep` | `perguntas-frequentes/` |
| `CHAT_CSA_QA_CACHE_MIN_SCORE` | limiar de similaridade para injetar uma entrada | `0.68` (`qa_cache.py`) |
| `CSA_MIN_INTERVAL_S` | intervalo mínimo entre requests ao portal | `3` (`csa_portal.py`) |
| `CSA_CACHE_DIR` | diretório do cache em disco do portal | `.cache/csa-web` |
| `CSA_CACHE_TTL_S` | validade do cache do portal | `3600` |
| `FRONTEND_PORT` | porta publicada do frontend no compose | `5173` |
| `VITE_CONSUMER_URL` | URL do consumer usada pelo frontend | `http://localhost:8002` |

Precedência do provedor de LLM: flags do CLI (`--provider`/`--model`) sobrepõem o ambiente, que sobrepõe os defaults do `factory.py`; o `.env` é aplicado por `python-dotenv` no start (`agent/factory.py`, `cli.py`).

## `pyproject.toml` — ferramentas

| Seção | Configuração |
|---|---|
| `[tool.ruff]` | `line-length = 120`, alvo `py310` |
| `[tool.ruff.lint]` | regras `E, F, I, B, C4, UP`; `E501` ignorado |
| `[tool.pytest.ini_options]` | `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| `[tool.uv]` / `[dependency-groups]` | ambiente gerenciado pelo uv; dev = pytest, pytest-asyncio, ruff, httpx |
| `[project.scripts]` | `chat-csa = "chat_csa.cli:app"` |

## Docker e Compose

O `Dockerfile` da raiz instala o pacote com `pip install .` (sem uv), inclui `curl` e `poppler-utils`, define `AGENT_CONFIG_DIR=.consumer`, `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `LLM_MODEL=gemma4:31b-cloud`, `HOST=0.0.0.0`, `PORT=8000`, expõe a porta 8000 e checa saúde com `curl -sf http://localhost:8000/health`.

O `docker-compose.yml` sobe dois serviços:

| Serviço | Build | Porta publicada | Aponta para |
|---|---|---|---|
| `consumer` | `.` | `${CONSUMER_PORT:-8002}` → 8000 | `AGENT_CONFIG_DIR=.consumer` |
| `frontend` | `./frontend` | `${FRONTEND_PORT:-5173}` → 80 | `VITE_CONSUMER_URL=http://localhost:${CONSUMER_PORT:-8002}` |

O consumer monta `./data` como volume e lê o `.env` via `env_file`; as variáveis de LLM têm fallback em cadeia (`CONSUMER_LLM_PROVIDER` → `LLM_PROVIDER` → `ollama`). A base de conhecimento **não** é montada: ela vem da API do GitHub (`KB_*`). O frontend tem Dockerfile próprio (build Vite → nginx) e recebe `VITE_CONSUMER_URL` como `ARG` de build.

## Frontend

- `frontend/.env.example` define `VITE_CONSUMER_URL=http://localhost:8002`.
- `frontend/.env.production` aponta `VITE_CONSUMER_URL` para a URL pública do backend. Ele também define `VITE_INGESTER_URL`, que **não é lido** por nenhum arquivo do frontend (`client.ts` só consulta `VITE_CONSUMER_URL`); a variável é resíduo da época em que existiam dois agentes.
- Override em runtime: o widget aceita `?consumerUrl=` na URL e `window.__CSA_CHAT_CONSUMER_URL__`, que têm precedência sobre a env de build (`frontend/src/api/client.ts`).

## Vercel e CI

- `vercel.json` (raiz) empacota `src/chat_csa/**` e `.consumer/**` na função Python apontada por `api/index.py`, com rewrite de tudo para o entrypoint.
- `frontend/vercel.json` faz o rewrite de SPA para `index.html`.
- Os segredos de deploy vivem como secrets do GitHub e são sincronizados para a Vercel pelo workflow `env-sync.yml` com `scripts/sync-vercel-env.sh` (allowlist de LLM + `KB_*`, sem imprimir valores). O fluxo está em [deploy.md](./deploy.md).

## Configuração do agente (`.consumer/`)

`AGENTS.md` e `skills/*/SKILL.md` são configuração viva: o system prompt é remontado a cada request a partir desses arquivos (`agent/prompt.py`), sem reiniciar o servidor. O conjunto de ferramentas vem de `CHAT_CSA_PORTAL_TOOLS` (`kb_list`/`kb_read` sempre; `web_csa_*` só quando ligado).

## Fontes

- `.env.example`
- `frontend/.env.example`, `frontend/.env.production`
- `pyproject.toml`
- `docker-compose.yml`, `Dockerfile`, `frontend/Dockerfile`
- `vercel.json`, `frontend/vercel.json`
- `src/chat_csa/kb.py`, `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/tools.py`, `src/chat_csa/qa_cache.py`, `src/chat_csa/csa_portal.py`
- `src/chat_csa/kb_upload.py`, `src/chat_csa/kb_convert.py`
- `frontend/src/api/client.ts`
- `scripts/sync-vercel-env.sh`
