# Deploy

Este documento cobre como o Chat CSA é publicado: os dois projetos na Vercel, o pipeline do GitHub Actions que faz o deploy automático, a sincronização de variáveis de ambiente e como a base de conhecimento remota é alimentada. Há também o caminho manual e a alternativa via Docker.

## Resumo para não-devs

O sistema tem dois sites publicados: a **API** (que responde às perguntas) e o **site do chat** (a página do botão flutuante). Publicar uma nova versão é automático: quando um membro da equipe envia código para a branch principal do GitHub, um robô de integração compila e publica os dois sites sozinho — e só publica se as verificações de qualidade passarem. A base de conhecimento não vai mais junto com o código: ela vive num branch separado (`data`) e é atualizada pelo time pelo endpoint de upload; o deploy não publica conteúdo.

## Projetos na Vercel

| Projeto | Diretório | Entrada | URL |
|---|---|---|---|
| `chat-csa-api` | raiz do repo | `api/index.py` (`@vercel/python`) | `https://chat-csa-api.vercel.app` |
| `chat-csa-web` | `frontend/` | SPA Vite + React | definida no painel da Vercel |

O `vercel.json` da raiz configura o build da função com `includeFiles: ["src/chat_csa/**", ".consumer/**"]` e faz rewrite de todas as rotas para `api/index.py`. O `api/index.py` insere `src/` no `sys.path`, aponta `AGENT_CONFIG_DIR` para o `.consumer` embutido e expõe o app como `handler`. O `frontend/vercel.json` só faz o rewrite de SPA para `index.html`.

A base de conhecimento **não** é embutida no deploy: ela é lida em runtime pela API do GitHub (branch `data`), configurada pelas variáveis `KB_*`. Sem `KB_REPO`/`KB_TOKEN` configurados, o chat responde sem base (não quebra).

## Pipeline (`.github/workflows/deploy.yml`)

Disparo: push em `main` ou `development`, e pull requests. A concorrência é por ref (`deploy-${{ github.ref }}`, cancel-in-progress), o workflow tem `contents: read` e roda dois jobs:

1. **`checks`** — `npm ci`, `npx oxlint src` e `npm run build` em `frontend/`; `pip install ruff && ruff check src` no backend. Qualquer falha bloqueia o deploy.
2. **`deploy`** — matriz com um item por projeto (`api` na raiz, `frontend/` em `frontend`). Push em `main` → `vercel deploy --prod`; qualquer outro ref → deploy de preview. PRs de fork são excluídas da condição porque não recebem secrets. O build é remoto na Vercel (sem `--prebuilt`) e o CLI é fixado em `vercel@59`.

Os tokens são **project-scoped** e o workflow não usa o link `.vercel/project.json`; a identificação vem das variáveis `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` do passo.

| Secret (GitHub) | Uso |
|---|---|
| `VERCEL_TOKEN_API` / `VERCEL_TOKEN_FRONTEND` | token do projeto Vercel |
| `VERCEL_ORG_ID_API` / `VERCEL_ORG_ID_FRONTEND` | id do escopo do projeto |
| `VERCEL_PROJECT_ID_API` / `VERCEL_PROJECT_ID_FRONTEND` | id do projeto |
| `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` | variáveis do backend sincronizadas para a Vercel |
| `KB_BACKEND`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL` | base de conhecimento remota sincronizada para a Vercel |

## Sincronização de ambiente (`env-sync.yml`)

Execução manual: **Actions → "Sync Vercel env" → Run workflow**, escolhendo `production`, `preview` ou `development`. O workflow instala o CLI, monta um `.env` temporário apenas com os secrets definidos (pulando ausentes) e chama `scripts/sync-vercel-env.sh <ambiente>`. Antes disso, descarta o `.vercel/project.json` versionado — link antigo de escopo de time que tokens project-scoped não conseguem usar; o projeto é identificado por `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID`.

O script aplica uma allowlist (`LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` + `KB_BACKEND`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL`) e **não imprime valores**. É idempotente nos dois caminhos: com `VERCEL_TOKEN` + `VERCEL_PROJECT_ID` definidos (CI), usa a API REST — remove as entradas anteriores do alvo com `DELETE` e grava com `POST` em `api.vercel.com` —, porque tokens project-scoped não conseguem rodar `vercel env`; localmente, cai para o CLI (`vercel env rm` + `vercel env add`). Em `production`, ele força `OLLAMA_BASE_URL=https://ollama.com` porque o `localhost` do `.env` local só vale para desenvolvimento; fora de `development`, força `KB_BACKEND=github`.

Para o preview da Vercel, configure ao menos `KB_BACKEND=github`, `KB_REPO`, `KB_BRANCH=data` e `KB_TOKEN` (leitura); `KB_WRITE_TOKEN` habilita o upload admin nesse ambiente.

## Scrape manual (`scrape-csa.yml`)

O workflow agora é **manual** (`workflow_dispatch`), sem agendamento e **sem commit**: roda `scripts/scrape_portal.py` via `uv sync --frozen`, grava `knowledge/raw/` no runner e publica a saída como artifact (`knowledge-raw`). Quem decide o que entra na base é o time, pelo upload (`POST /kb/upload`).

## Caminho manual

```bash
make deploy-env        # scripts/sync-vercel-env.sh production
make deploy-api        # raiz do repo: npx vercel deploy --prod --yes
make deploy-frontend   # frontend/: npx vercel deploy --prod --yes
```

Pré-requisito: `npx vercel link` uma vez em cada diretório (raiz e `frontend/`) — na Vercel, sem os tokens project-scoped do CI.

## Alternativa: Docker

O `Dockerfile` da raiz gera uma imagem única do backend (porta 8000, `HEALTHCHECK` em `/health`, `AGENT_CONFIG_DIR=.consumer`) e `docker compose up` sobe consumer e frontend. É o caminho para hospedagem própria/single-host, não o usado na Vercel — os detalhes de variáveis estão em [configuracao.md](./configuracao.md).

## Limitações do ambiente serverless

- O `auth_store` é em memória: em cold start ou múltiplas instâncias da função, usuários e tokens resetam — inclusive os que protegem `/kb/upload`.
- O cache da base (TTL padrão 60s) vive na memória de cada instância; uploads aparecem na leitura após o TTL ou em uma nova instância.
- O filesystem da função é somente leitura e efêmero: nada da base é gravado em disco; o backend github não persiste arquivos localmente.
- O scraper é manual e roda no GitHub Actions (não roda na Vercel).

## Fontes

- `.github/workflows/deploy.yml`, `.github/workflows/env-sync.yml`, `.github/workflows/scrape-csa.yml`
- `vercel.json`, `frontend/vercel.json`, `api/index.py`
- `scripts/sync-vercel-env.sh`, `scripts/scrape_portal.py`
- `Makefile` (alvos `deploy-*`), `Dockerfile`, `docker-compose.yml`
- `README.md` (seção "Deploy")
