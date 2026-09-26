# Estrutura do repositório

Este documento é o mapa do repositório: o que vive em cada diretório, como o layout `src/` se conecta ao entrypoint de deploy e onde ficam configuração de agentes, bundle de conhecimento, frontend e testes. Ele responde "onde eu mexo?" — não detalha cada arquivo, que é assunto das demais páginas.

## Visão geral

```text
chat-csa/
├── src/chat_csa/        # pacote Python (backend + agentes)
│   ├── agent/           # fábrica do agente, system prompt, ferramentas
│   ├── server/          # FastAPI (app, auth, modelos, painel admin FastHTML)
│   ├── cli.py           # entrypoint `chat-csa serve|print-prompt`
│   ├── csa_portal.py    # cliente read-only do portal CSA/UEFS
│   └── qa_cache.py      # recuperação de FAQ curada em Markdown
├── api/index.py         # entrypoint ASGI da Vercel (importa o pacote)
├── .ingester/           # AGENTS home do agente ingester (AGENTS.md + skills/)
├── .consumer/           # AGENTS home do agente consumer (AGENTS.md + skills/)
├── knowledge/           # bundle OKF curado (conteúdo, não documentação)
├── scripts/             # scrape do portal e sincronização de env da Vercel
├── tests/               # suíte offline (pytest)
├── examples/            # clientes de exemplo (curl, OpenAI SDK, Ollama)
├── docs/                # documentação do projeto
├── frontend/            # SPA React/Vite do consumer + embed.js
├── .github/workflows/   # deploy, sync de env e scrape periódico
├── Makefile             # atalhos de DX
├── pyproject.toml       # dependências, scripts, ruff e pytest
├── Dockerfile           # imagem do backend (Dockerfile próprio do frontend em frontend/)
├── docker-compose.yml   # ingester + consumer + frontend
└── vercel.json          # build do backend na Vercel
```

## Backend (`src/`)

O pacote segue o layout `src/`, então o código importável fica em `src/chat_csa/` e o `pyproject.toml` declara `packages = ["src/chat_csa"]` (`[tool.hatch.build.targets.wheel]`). Dentro dele:

| Caminho | Responsabilidade |
|---|---|
| `src/chat_csa/agent/factory.py` | escolhe o provedor (`ollama`/`openai`/`fake`) e monta o agente |
| `src/chat_csa/agent/prompt.py` | concatena `AGENTS.md` + `skills/*/SKILL.md` no system prompt |
| `src/chat_csa/agent/tools.py` | ferramentas `read`/`write`/`edit`/`bash` + `web_csa_fetch`/`web_csa_search` |
| `src/chat_csa/server/app.py` | rotas HTTP compatíveis com OpenAI e Ollama |
| `src/chat_csa/server/auth.py` | usuários/tokens em memória do ingester |
| `src/chat_csa/server/admin.py` | painel FastHTML montado em `/admin` |
| `src/chat_csa/server/models.py` | modelos Pydantic da API |
| `src/chat_csa/qa_cache.py` | carrega e pontua entradas de FAQ curada como referência de prompt |
| `src/chat_csa/csa_portal.py` | fetch/busca com allowlist, rate-limit, backoff e cache em disco |
| `src/chat_csa/cli.py` | comando `chat-csa serve` e `chat-csa print-prompt` |

O `api/index.py` é o adaptador para a runtime Python da Vercel: insere `src/` no `sys.path`, aponta `AGENT_CONFIG_DIR` para o `.ingester` embutido e expõe o mesmo app FastAPI como `handler`. É por isso que o `vercel.json` empacota `src/chat_csa/**` e `.ingester/**` junto da função.

## AGENTS homes (`.ingester/` e `.consumer/`)

Cada agente tem um diretório próprio com `AGENTS.md` e `skills/`; o `agent/prompt.py` lê tudo a cada request (hot-reload, sem reiniciar o servidor):

```text
.ingester/
├── AGENTS.md
└── skills/
    ├── csa-ingest/SKILL.md                  # fluxo de ingestão e curadoria
    ├── ingester-incremental-ingest/SKILL.md # ingestão incremental por data
    └── okf/SKILL.md (+ references/)         # formato OKF
.consumer/
├── AGENTS.md
└── skills/
    ├── csa-query/SKILL.md                # fluxo de resposta do consumer
    ├── csa-portal-lookup/SKILL.md        # busca de documentos no portal
    └── name-lookup-in-lists/SKILL.md     # consulta de nomes em listas
```

O nome do diretório decide o conjunto de ferramentas: ingester recebe CRUD completo + ferramentas do portal; consumer é somente leitura (`tools_for_config`, em `agent/factory.py`).

## Bundle de conhecimento (`knowledge/`)

`knowledge/` é um bundle **OKF** com um conceito por arquivo Markdown (frontmatter YAML + corpo). Índices `index.md` não têm frontmatter; `log.md` registra as alterações. As categorias são `editais/`, `cronogramas/`, `procedimentos/`, `modalidades/` e `perguntas-frequentes/`. Este diretório é **conteúdo curado** — versionado no Git, mas não é documentação do projeto e não deve ser copiado para `docs/` (ver `docs/adr/001-versionamento-base-conhecimento.md`).

## Frontend (`frontend/`)

| Caminho | Responsabilidade |
|---|---|
| `frontend/src/App.tsx` | decide modo página vs. embutido (`?embed=1`) |
| `frontend/src/api/client.ts` | cliente SSE do consumer (`chatCompletionStream`) |
| `frontend/src/components/chat/` | widget completo (header, status, sugestões, fontes, CSS) |
| `frontend/public/embed.js` | snippet que cria o iframe do widget em páginas externas |
| `frontend/nginx.conf` | serve a SPA com fallback para `index.html` |
| `frontend/vercel.json` | rewrite de SPA na Vercel |

## Scripts, testes e exemplos

- `scripts/scrape_portal.py` monta a lista de URLs do SiSU vigente, raspa para `knowledge/raw/` com frontmatter de proveniência e é o trabalho do workflow `scrape-csa.yml`.
- `scripts/sync-vercel-env.sh` sincroniza uma allowlist de variáveis do `.env` para a Vercel, sem imprimir valores.
- `tests/` cobre ferramentas, servidor, portal, cache de QA, qualidade de citação e regressão do painel admin (veja [testes.md](./testes.md)).
- `examples/` traz clientes mínimos (`curl.md`, `openai_client.py`, `ollama_client.py`) apontando para `:8001`.

## Decisão de layout

O `src/` evita que o pacote seja importado por acidente a partir da raiz e casa com o empacotamento do hatchling; o `api/index.py` existe porque a Vercel exige um arquivo de entrada dentro da função — ele não duplica lógica, só ajusta `sys.path` e a variável de config dir antes de importar `chat_csa.server.app`. Os diretórios de agente ficam na raiz (e não dentro do pacote) porque funcionam como "config", não como código: são editados durante a operação e recarregados a quente.

## Fontes

- Árvore real do repositório (listagem de arquivos)
- `pyproject.toml`
- `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/prompt.py`
- `api/index.py`, `vercel.json`
- `.ingester/AGENTS.md`, `.consumer/AGENTS.md`
- `knowledge/index.md`
- `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/public/embed.js`
- `scripts/scrape_portal.py`
