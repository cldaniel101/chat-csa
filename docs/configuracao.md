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
| `CHAT_CSA_ADMIN_USERNAME` | usuário principal do painel | vazio (admin desabilitado) |
| `CHAT_CSA_ADMIN_PASSWORD_HASH` | hash scrypt da senha administrativa (senha com no mínimo 12 caracteres) | vazio; gere com `scripts/hash_admin_password.py` |
| `CHAT_CSA_AUTH_SECRET` | segredo HMAC das sessões (mínimo de 32 bytes) | vazio |
| `CHAT_CSA_AUTH_SESSION_TTL` | validade da sessão em segundos | `28800` |
| `CHAT_CSA_CORS_ORIGINS` | origens autorizadas, separadas por vírgula | origens locais do Vite |
| `CHAT_CSA_UNANSWERED_SECRET` | chave (mínimo de 32 bytes) das perguntas sem resposta | cai em `CHAT_CSA_AUTH_SECRET` |
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
| `CHAT_CSA_EMAIL_API_URL` | endpoint HTTPS da API usada pelo alerta de atualização | vazio (`update_notification.py`) |
| `CHAT_CSA_EMAIL_API_TOKEN` | token sigiloso enviado no corpo JSON da API de e-mail | vazio (`update_notification.py`) |
| `CHAT_CSA_UPDATE_NOTIFICATION_TO` | destinatário do aviso de revisão manual | vazio (`update_notification.py`) |
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
- `frontend/.env.production` aponta `VITE_CONSUMER_URL` para a URL pública do backend; nenhuma credencial administrativa é incluída no bundle.
- Override em runtime: o widget aceita `?consumerUrl=` na URL e `window.__CSA_CHAT_CONSUMER_URL__`, que têm precedência sobre a env de build (`frontend/src/api/client.ts`).

## Vercel e CI

- `vercel.json` (raiz) empacota `src/chat_csa/**` e `.consumer/**` na função Python apontada por `api/index.py`, com rewrite de tudo para o entrypoint.
- `frontend/vercel.json` faz o rewrite de SPA para `index.html`.
- Conforme a [ADR-003](./adr/003-simplificacao-arquitetura-devops.md), a topologia adota 2 projetos na Vercel (`chat-csa-api` e `chat-csa-web`). As variáveis de runtime (`LLM_*`, `KB_*`, `CHAT_CSA_ADMIN_*`, `CHAT_CSA_AUTH_*`, `CHAT_CSA_CORS_ORIGINS` e `VITE_CONSUMER_URL`) são configuradas diretamente no painel de Environment Variables da Vercel para os ambientes Production e Preview, dispensando scripts de sincronização via REST. O CI utiliza 5 segredos de deploy (`VERCEL_TOKEN_API`, `VERCEL_TOKEN_FRONTEND`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID_API`, `VERCEL_PROJECT_ID_FRONTEND`), com um token project-scoped por projeto ([ADR-004](./adr/004-tokens-deploy-project-scoped.md)). A Vercel instala apenas `api/requirements.txt`: dependências novas de runtime precisam entrar nele **e** no `pyproject.toml`, senão o CI passa e a função quebra em produção.
- O workflow manual `scrape-csa.yml` recebe `CHAT_CSA_EMAIL_API_URL`, `CHAT_CSA_EMAIL_API_TOKEN` e `CHAT_CSA_UPDATE_NOTIFICATION_TO` exclusivamente como *repository secrets*. A variável pública opcional `CHAT_CSA_ADMIN_PANEL_URL` troca o link do painel no aviso; sem ela, usa `https://chat-csa-web.vercel.app/admin`. `SCRAPE_RUNNER` pode indicar o label de um runner Linux com acesso ao portal; sem a variável, o workflow usa `ubuntu-latest`.

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
