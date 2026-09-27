# Estrutura do repositório

Este documento é o mapa do repositório: o que vive em cada diretório, como o layout `src/` se conecta ao entrypoint de deploy e onde ficam configuração do agente, base de conhecimento, frontend e testes. Ele responde "onde eu mexo?" — não detalha cada arquivo, que é assunto das demais páginas.

## Visão geral

```text
chat-csa/
├── src/chat_csa/        # pacote Python (backend + agente)
│   ├── agent/           # fábrica do agente, system prompt, ferramentas
│   ├── server/          # FastAPI (app, auth, modelos, endpoints /kb/*)
│   ├── cli.py           # entrypoint `chat-csa serve|print-prompt`
│   ├── kb.py            # cliente da base remota (github/local, renderizador, cache)
│   ├── kb_upload.py     # POST /kb/upload: valida, converte e monta o commit atômico
│   ├── kb_convert.py    # conversão por tipo (pdf, imagem, csv/tsv, texto) em Markdown
│   ├── kb_okf.py        # conceito OKF (frontmatter, caminho, índices de seção e raiz)
│   ├── csa_portal.py    # cliente read-only do portal CSA/UEFS
│   └── qa_cache.py      # recuperação de FAQ curada na base remota
├── api/index.py         # entrypoint ASGI da Vercel (importa o pacote)
├── .consumer/           # AGENTS home do agente consumer (AGENTS.md + skills/)
├── scripts/             # scrape do portal e sincronização de env da Vercel
├── tests/               # suíte offline (pytest)
├── examples/            # clientes de exemplo (curl, OpenAI SDK, Ollama)
├── docs/                # documentação do projeto
├── frontend/            # SPA React/Vite do consumer + embed.js
├── .github/workflows/   # deploy, sync de env e scrape manual
├── Makefile             # atalhos de DX
├── pyproject.toml       # dependências, scripts, ruff e pytest
├── Dockerfile           # imagem do backend (Dockerfile próprio do frontend em frontend/)
├── docker-compose.yml   # consumer + frontend
└── vercel.json          # build do backend na Vercel
```

> A base de conhecimento **não** vive nos branches de código: ela fica no branch órfão `data` (ver [arquitetura.md](./arquitetura.md)). A pasta `knowledge/` é apenas uma base local de dev/testes, gitignored.

## Backend (`src/`)

O pacote segue o layout `src/`, então o código importável fica em `src/chat_csa/` e o `pyproject.toml` declara `packages = ["src/chat_csa"]` (`[tool.hatch.build.targets.wheel]`). Dentro dele:

| Caminho | Responsabilidade |
|---|---|
| `src/chat_csa/agent/factory.py` | escolhe o provedor (`ollama`/`openai`/`fake`) e monta o agente |
| `src/chat_csa/agent/prompt.py` | concatena `AGENTS.md` + `skills/*/SKILL.md` no system prompt |
| `src/chat_csa/agent/tools.py` | ferramentas `kb_list`/`kb_read` + `web_csa_fetch`/`web_csa_search` (opcionais) |
| `src/chat_csa/kb.py` | cliente da base remota: `list`/`read`/`write`, backends github/local, renderizador e cache TTL |
| `src/chat_csa/kb_upload.py` | processa o `/kb/upload`: valida caminhos e orçamento, converte o lote e monta o commit atômico |
| `src/chat_csa/kb_convert.py` | conversão por tipo em Markdown: pdf (texto por layout + páginas rasterizadas), imagem, csv/tsv e texto |
| `src/chat_csa/kb_okf.py` | conceitos OKF e índices: frontmatter do template, normalização de caminho, índice de seção e raiz |
| `src/chat_csa/server/app.py` | rotas HTTP compatíveis com OpenAI e Ollama + montagem do `/kb/*` |
| `src/chat_csa/server/kb_api.py` | endpoints admin `/kb/list`, `/kb/file`, `/kb/upload` |
| `src/chat_csa/server/auth.py` | usuários/tokens em memória (admin) |
| `src/chat_csa/server/models.py` | modelos Pydantic da API |
| `src/chat_csa/qa_cache.py` | carrega e pontua entradas de FAQ curada como referência de prompt |
| `src/chat_csa/csa_portal.py` | fetch/busca com allowlist, rate-limit, backoff e cache em disco |
| `src/chat_csa/cli.py` | comando `chat-csa serve` e `chat-csa print-prompt` |

O `api/index.py` é o adaptador para a runtime Python da Vercel: insere `src/` no `sys.path`, aponta `AGENT_CONFIG_DIR` para o `.consumer` embutido e expõe o mesmo app FastAPI como `handler`. É por isso que o `vercel.json` empacota `src/chat_csa/**` e `.consumer/**` junto da função.

## AGENTS home (`.consumer/`)

O agente tem um diretório próprio com `AGENTS.md` e `skills/`; o `agent/prompt.py` lê tudo a cada request (hot-reload, sem reiniciar o servidor):

```text
.consumer/
├── AGENTS.md
└── skills/
    ├── csa-query/SKILL.md                # fluxo de resposta do consumer
    ├── csa-portal-lookup/SKILL.md        # busca de documentos no portal
    └── name-lookup-in-lists/SKILL.md     # consulta de nomes em listas
```

O conjunto de ferramentas é único (`kb_list`/`kb_read` + portal opcional via `CHAT_CSA_PORTAL_TOOLS`), montado em `tools_for_config` (`agent/factory.py`).

## Base de conhecimento (branch `data`)

A base é um bundle **OKF** com um conceito por arquivo Markdown (frontmatter YAML + corpo), na raiz do branch órfão `data`. Índices `index.md` não têm frontmatter. As categorias são `editais/`, `cronogramas/`, `procedimentos/`, `modalidades/` e `perguntas-frequentes/`. O branch nasce com um `README.md` explicando o fluxo; o time envia conteúdo por `POST /kb/upload`, que converte cada arquivo num conceito OKF. Decisão registrada em `docs/adr/002-base-conhecimento-branch-data.md`.

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

- `scripts/scrape_portal.py` monta a lista de URLs do SiSU vigente e raspa para `knowledge/raw/` com frontmatter de proveniência; o workflow `scrape-csa.yml` virou manual e publica a saída como artifact (sem commit).
- `scripts/sync-vercel-env.sh` sincroniza uma allowlist de variáveis (LLM + `KB_*`) do `.env` para a Vercel, sem imprimir valores.
- `tests/` cobre ferramentas (`kb_list`/`kb_read`), servidor, cliente da base, portal, cache de QA e qualidade de citação (veja [testes.md](./testes.md)).
- `examples/` traz clientes mínimos (`curl.md`, `openai_client.py`, `ollama_client.py`) apontando para `:8002`.

## Decisão de layout

O `src/` evita que o pacote seja importado por acidente a partir da raiz e casa com o empacotamento do hatchling; o `api/index.py` existe porque a Vercel exige um arquivo de entrada dentro da função — ele não duplica lógica, só ajusta `sys.path` e a variável de config dir antes de importar `chat_csa.server.app`. O diretório do agente fica na raiz (e não dentro do pacote) porque funciona como "config", não como código: é editado durante a operação e recarregado a quente.

## Fontes

- Árvore real do repositório (listagem de arquivos)
- `pyproject.toml`
- `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/prompt.py`
- `src/chat_csa/kb.py`, `src/chat_csa/server/kb_api.py`
- `src/chat_csa/kb_upload.py`, `src/chat_csa/kb_convert.py`, `src/chat_csa/kb_okf.py`
- `api/index.py`, `vercel.json`
- `.consumer/AGENTS.md`
- `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/public/embed.js`
- `scripts/scrape_portal.py`
