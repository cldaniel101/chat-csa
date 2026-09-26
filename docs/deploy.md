# Deploy

Este documento cobre como o Chat CSA é publicado: os dois projetos na Vercel, o pipeline do GitHub Actions que faz o deploy automático, a sincronização de variáveis de ambiente e o robô que mantém a base de conhecimento atualizada. Há também o caminho manual e a alternativa via Docker.

## Resumo para não-devs

O sistema tem dois sites publicados: a **API** (que responde às perguntas) e o **site do chat** (a página do botão flutuante). Publicar uma nova versão é automático: quando um membro da equipe envia código para a branch principal do GitHub, um robô de integração compila e publica os dois sites sozinho — e só publica se as verificações de qualidade passarem. Existe também um robô separado que, a cada 12 horas, baixa as novidades do portal da CSA e as guarda na base de conhecimento, garantindo que o chat responda com informação fresca.

## Projetos na Vercel

| Projeto | Diretório | Entrada | URL |
|---|---|---|---|
| `chat-csa-api` | raiz do repo | `api/index.py` (`@vercel/python`) | `https://chat-csa-api.vercel.app` |
| `chat-csa-web` | `frontend/` | SPA Vite + React | definida no painel da Vercel |

O `vercel.json` da raiz configura o build da função com `includeFiles: ["src/chat_csa/**", ".ingester/**"]` e faz rewrite de todas as rotas para `api/index.py`. O `api/index.py` insere `src/` no `sys.path`, aponta `AGENT_CONFIG_DIR` para o `.ingester` embutido e expõe o app como `handler`. O `frontend/vercel.json` só faz o rewrite de SPA para `index.html`.

## Pipeline (`.github/workflows/deploy.yml`)

Disparo: push em `main` ou `development`, e pull requests. A concorrência é por ref (`deploy-${{ github.ref }}`, cancel-in-progress), o workflow tem `contents: read` e roda dois jobs:

1. **`checks`** — `npm ci`, `npx oxlint src` e `npm run build` em `frontend/`; `pip install ruff && ruff check src` no backend. Qualquer falha bloqueia o deploy.
2. **`deploy`** — matriz com um item por projeto (`api` na raiz, `frontend/` em `frontend`). Push em `main` → `vercel deploy --prod`; qualquer outro ref → deploy de preview. PRs de fork são excluídas da condição porque não recebem secrets. O build é remoto na Vercel (sem `--prebuilt`) e o CLI é fixado em `vercel@59`.

Os tokens são **project-scoped** e o workflow não usa o link `.vercel/project.json`; a identificação vem das variáveis `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` do passo.

| Secret (GitHub) | Uso |
|---|---|
| `VERCEL_TOKEN_API` / `VERCEL_TOKEN_FRONTEND` | token do projeto Vercel |
| `VERCEL_ORG_ID_API` / `VERCEL_ORG_ID_FRONTEND` | id da equipe |
| `VERCEL_PROJECT_ID_API` / `VERCEL_PROJECT_ID_FRONTEND` | id do projeto |
| `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` | variáveis do backend sincronizadas para a Vercel |

## Sincronização de ambiente (`env-sync.yml`)

Execução manual: **Actions → "Sync Vercel env" → Run workflow**, escolhendo `production`, `preview` ou `development`. O workflow instala o CLI, monta um `.env` temporário apenas com os secrets definidos (pulando ausentes) e chama `scripts/sync-vercel-env.sh <ambiente>`.

O script aplica uma allowlist de 5 chaves (`LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`), **não imprime valores** e é idempotente (`vercel env rm` + `vercel env add`). Em `production`, ele força `OLLAMA_BASE_URL=https://ollama.com` porque o `localhost` do `.env` local só vale para desenvolvimento.

## Scrape periódico (`scrape-csa.yml`)

Roda `scripts/scrape_portal.py` via `uv sync --frozen`, grava `knowledge/raw/` e commita de volta com `github-actions[bot]` (permissão `contents: write`). O agendamento é `0 9,21 * * *` UTC — 06h e 18h em Brasília — e há disparo manual para testes. Se nada mudou, o job encerra sem commit; a concorrência (`group: scrape-csa`) evita dois pushes simultâneos.

## Caminho manual

```bash
make deploy-env        # scripts/sync-vercel-env.sh production
make deploy-api        # raiz do repo: npx vercel deploy --prod --yes
make deploy-frontend   # frontend/: npx vercel deploy --prod --yes
```

Pré-requisito: `npx vercel link` uma vez em cada diretório (raiz e `frontend/`) — na Vercel, sem os tokens project-scoped do CI.

## Alternativa: Docker

O `Dockerfile` da raiz gera uma imagem única do backend (porta 8000, `HEALTHCHECK` em `/health`, `AGENT_CONFIG_DIR` configurável em runtime) e `docker compose up` sobe ingester, consumer e frontend. É o caminho para hospedagem própria/single-host, não o usado na Vercel — os detalhes de variáveis estão em [configuracao.md](./configuracao.md).

## Limitações do ambiente serverless

- O `auth_store` é em memória: em cold start ou múltiplas instâncias da função, usuários e sessões do `/admin` resetam. Para o cookie de sessão funcionar em https, defina `ADMIN_COOKIE_SECURE=1`.
- Sem `CHAT_CSA_ADMIN_SECRET_KEY`, a chave de sessão do FastHTML é gerada por cold start e derruba sessões; a variável existe para estabilizar isso.
- O scraper depende de commit de volta no repositório (não roda na Vercel).

## Fontes

- `.github/workflows/deploy.yml`, `.github/workflows/env-sync.yml`, `.github/workflows/scrape-csa.yml`
- `vercel.json`, `frontend/vercel.json`, `api/index.py`
- `scripts/sync-vercel-env.sh`, `scripts/scrape_portal.py`
- `Makefile` (alvos `deploy-*`), `Dockerfile`, `docker-compose.yml`
- `README.md` (seção "Deploy")
