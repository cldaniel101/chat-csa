# Deploy

Este documento cobre como o Chat CSA é publicado: os dois projetos na Vercel, o pipeline do GitHub Actions que faz o deploy automático, a sincronização de variáveis de ambiente e como a base de conhecimento remota é alimentada. Há também o caminho manual e a alternativa via Docker.

## Resumo para não-devs

O sistema tem dois sites publicados: a **API** (que responde às perguntas) e o **site do chat** (a página do botão flutuante). Publicar uma nova versão é automático: quando um membro da equipe envia código para a branch principal do GitHub, um robô de integração compila e publica os dois sites sozinho — e só publica se as verificações de qualidade passarem. A base de conhecimento não vai mais junto com o código: ela vive num branch separado (`data`) e é atualizada pelo time pelo endpoint de upload; o deploy não publica conteúdo.

## Projetos na Vercel

| Projeto | Diretório | Entrada | URL |
|---|---|---|---|
| `chat-csa-api` | raiz do repo | `api/index.py` (`@vercel/python`) | `https://chat-csa-api.vercel.app` |
| `chat-csa-web` | `frontend/` | SPA Vite + React | definida no painel da Vercel |
| `chat-csa-api-preview` | raiz do repo | idem (staging) | `https://chat-csa-api-preview.vercel.app` |
| `chat-csa-web-preview` | `frontend/` | idem (staging) | `https://chat-csa-web-preview.vercel.app` |

Cada ambiente tem o **seu par** de projetos, porque um deploy `--prod` promove todos os domínios do projeto: o par principal serve produção (`main`) e o par de staging serve o preview (`development`), publicado com `--prod` para ter URL fixa.

O `vercel.json` da raiz configura o build da função com `includeFiles: ["src/chat_csa/**", ".consumer/**"]` e faz rewrite de todas as rotas para `api/index.py`. O `api/index.py` insere `src/` no `sys.path`, aponta `AGENT_CONFIG_DIR` para o `.consumer` embutido e expõe o app como `handler`. O `frontend/vercel.json` só faz o rewrite de SPA para `index.html`.

A base de conhecimento **não** é embutida no deploy: ela é lida em runtime pela API do GitHub (branch `data`), configurada pelas variáveis `KB_*`. Sem `KB_REPO`/`KB_TOKEN` configurados, o chat responde sem base (não quebra).

## Escopo e propriedade

Os quatro projetos vivem no **escopo de um time** — `dev-davmg`, id `team_a1g9RHULTlOEdkqTUhGZwhGF` —, não no escopo pessoal de quem os criou: o time é o dono e a conta pessoal é apenas um acesso. É isso que faz o deploy sobreviver à saída de uma pessoa, **desde que o time tenha mais de um owner**. A transferência de um projeto entre escopos é feita no painel da Vercel (Project → Settings → Transfer).

Os secrets `VERCEL_ORG_ID_*` precisam conter o id desse time. Se um projeto for movido para um escopo pessoal (ou o secret apontar para um), o deploy falha com `Project not found` mesmo com token e project id válidos — foi exatamente o que aconteceu em 27/09/2026, quando o `VERCEL_ORG_ID_API` ficou com um id de escopo pessoal.

O `.vercel/project.json` versionado (raiz e `frontend/`) existe para o **deploy manual local**; o CI identifica o projeto por `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` e ignora o link.

### Se o acesso ao deploy for perdido

1. Autenticar (`npx vercel login`) com uma conta que tenha acesso ao time.
2. Localizar ou recriar os quatro projetos — `chat-csa-api` (raiz), `chat-csa-web` (`frontend/`), `chat-csa-api-preview` (raiz) e `chat-csa-web-preview` (`frontend/`) — com `npx vercel link` em cada diretório.
3. Atualizar os secrets do repositório com os ids dos `project.json` recém-gerados: `VERCEL_PROJECT_ID_API`, `VERCEL_PROJECT_ID_FRONTEND`, `VERCEL_PROJECT_ID_API_PREVIEW`, `VERCEL_PROJECT_ID_FRONTEND_PREVIEW` e `VERCEL_ORG_ID_API`/`VERCEL_ORG_ID_FRONTEND` (o id do time), além de tokens project-scoped novos em `VERCEL_TOKEN_API`, `VERCEL_TOKEN_FRONTEND`, `VERCEL_TOKEN_API_PREVIEW` e `VERCEL_TOKEN_FRONTEND_PREVIEW`.
4. Recriar a variável de produção do site de staging (`chat-csa-web-preview` → Production → `VITE_CONSUMER_URL=https://chat-csa-api-preview.vercel.app`).
5. Rodar o workflow **Sync Vercel env** (`workflow_dispatch`) para reenviar as variáveis de runtime aos dois projetos de API.
6. Confirmar com um push em `development` (staging) e, depois, em `main` (produção).

## Pipeline (`.github/workflows/deploy.yml`)

Disparo: push em `main` ou `development`, e pull requests. A concorrência é por ref (`deploy-${{ github.ref }}`, cancel-in-progress), o workflow tem `contents: read` e roda dois jobs:

1. **`checks`** — `npm ci`, `npx oxlint src` e `npm run build` em `frontend/`; `pip install ruff && ruff check src` no backend. Qualquer falha bloqueia o deploy.
2. **`deploy`** — matriz com um item por projeto (`api` na raiz, `frontend/` em `frontend`), com três caminhos: push em `main` → `vercel deploy --prod` no par principal; push em `development` → `vercel deploy --prod` no par de **staging**; pull request → preview descartável no par principal. PRs de fork são excluídas da condição porque não recebem secrets. O build é remoto na Vercel (sem `--prebuilt`) e o CLI é fixado em `vercel@59`.

Os tokens são **project-scoped** e o workflow não usa o link `.vercel/project.json`; a identificação vem das variáveis `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` do passo.

| Secret (GitHub) | Uso |
|---|---|
| `VERCEL_TOKEN_API` / `VERCEL_TOKEN_FRONTEND` | token do projeto do par principal |
| `VERCEL_TOKEN_API_PREVIEW` / `VERCEL_TOKEN_FRONTEND_PREVIEW` | token do projeto do par de staging |
| `VERCEL_ORG_ID_API` / `VERCEL_ORG_ID_FRONTEND` | id do escopo (time) dono dos quatro projetos |
| `VERCEL_PROJECT_ID_API` / `VERCEL_PROJECT_ID_FRONTEND` | id de cada projeto do par principal |
| `VERCEL_PROJECT_ID_API_PREVIEW` / `VERCEL_PROJECT_ID_FRONTEND_PREVIEW` | id de cada projeto do par de staging |
| `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` | variáveis do backend sincronizadas para a Vercel |
| `KB_BACKEND`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL` | base de conhecimento remota sincronizada para a Vercel |

### Preview do site e da API

O frontend é um build estático: o Vite **embute** a URL da API em tempo de build (`import.meta.env.VITE_CONSUMER_URL`), e a variável de ambiente tem prioridade sobre o `.env`. O `.env.production` versionado aponta para a produção (`https://chat-csa-api.vercel.app`) — o correto para o deploy de `main`.

O preview vive no **par de staging** (`chat-csa-api-preview` / `chat-csa-web-preview`), publicado com `--prod` a cada push em `development`: são produções paralelas, com URL fixa, usadas só como preview. O site de staging é compilado com `VITE_CONSUMER_URL=https://chat-csa-api-preview.vercel.app` (variável de ambiente de **Production** do próprio projeto), então ele sempre fala com a API de staging — sem alias e sem passo manual.

Os previews de PR continuam no par principal, com URL descartável; o site usa o `VITE_CONSUMER_URL` do ambiente **Preview** do `chat-csa-web`, que também aponta para a API de staging.

Em qualquer URL de preview, dá para apontar o site para uma API específica na hora: `?consumerUrl=https://<deployment-da-api>.vercel.app` (lido por `runtimeConsumerUrl()` em `frontend/src/api/client.ts`).

### Bootstrap: subir os ambientes do zero

1. Criar os quatro projetos no time (`dev-davmg`) — `chat-csa-api` e `chat-csa-api-preview` a partir da raiz do repo, `chat-csa-web` e `chat-csa-web-preview` a partir de `frontend/` (`npx vercel link` em cada diretório cria o link local).
2. Criar em **Account Settings → Tokens** um token **project-scoped** por projeto (mesmo caminho usado para os tokens atuais) e registrá-los no GitHub: `VERCEL_TOKEN_API`, `VERCEL_TOKEN_FRONTEND`, `VERCEL_TOKEN_API_PREVIEW`, `VERCEL_TOKEN_FRONTEND_PREVIEW`.
3. Registrar os ids: `VERCEL_ORG_ID_API`/`VERCEL_ORG_ID_FRONTEND` (o id do time — os quatro projetos vivem nele) e `VERCEL_PROJECT_ID_*` (um por projeto, copiado do `.vercel/project.json`).
4. Apontar os sites para as APIs: `chat-csa-web-preview` → **Production** → `VITE_CONSUMER_URL=https://chat-csa-api-preview.vercel.app`; `chat-csa-web` → **Preview** → mesma URL (previews de PR).
5. Rodar **Sync Vercel env** (`workflow_dispatch`, input `production`) para os dois projetos de API; para QA no par principal, rodar também com `preview`.
6. Push em `development` (staging) e em `main` (produção).

Os valores de `LLM_*`/`KB_*` vivem nos secrets do GitHub; os **ids não são segredos** (já estão versionados nos `project.json`) e os tokens são.

## Sincronização de ambiente (`env-sync.yml`)

Execução manual: **Actions → "Sync Vercel env" → Run workflow**, escolhendo `production`, `preview` ou `development`. O workflow instala o CLI, monta um `.env` temporário apenas com os secrets definidos (pulando ausentes) e chama `scripts/sync-vercel-env.sh <ambiente>`. Antes disso, descarta o `.vercel/project.json` versionado — link antigo de escopo de time que tokens project-scoped não conseguem usar; o projeto é identificado por `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID`.

O script aplica uma allowlist (`LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` + `KB_BACKEND`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL`) e **não imprime valores**. É idempotente nos dois caminhos: com `VERCEL_TOKEN` + `VERCEL_PROJECT_ID` definidos (CI), usa a API REST — remove as entradas anteriores do alvo com `DELETE` e grava com `POST` em `api.vercel.com` —, porque tokens project-scoped não conseguem rodar `vercel env`; localmente, cai para o CLI (`vercel env rm` + `vercel env add`). Em `production`, ele força `OLLAMA_BASE_URL=https://ollama.com` porque o `localhost` do `.env` local só vale para desenvolvimento; fora de `development`, força `KB_BACKEND=github`.

Para o preview da Vercel, configure ao menos `KB_BACKEND=github`, `KB_REPO`, `KB_BRANCH=data` e `KB_TOKEN` (leitura); `KB_WRITE_TOKEN` habilita o upload admin nesse ambiente.

O par de staging é sincronizado **sempre** no alvo `production` do próprio projeto, porque `development` publica com `--prod` — o input do workflow vale só para o projeto principal.

Enquanto o secret `VERCEL_TOKEN_API_PREVIEW` não existir, o workflow **pula** o sync do projeto de staging com um aviso (`::warning::`) em vez de falhar; ao criar o token, o passo volta a rodar sozinho.

**Mudar variável de ambiente exige novo deploy**: a Vercel injeta as variáveis na criação do deployment; um deployment antigo continua com as antigas. Foi o que aconteceu com o `chat-csa-api-preview`, que subiu sem `LLM_*`/`KB_*` e respondia 500 ("All connection attempts failed" no site) até ser reenviado depois do sync.

### Como verificar depois de mexer

```bash
curl -s https://chat-csa-api-preview.vercel.app/health   # {"status":"ok",...}
curl -s https://chat-csa-api-preview.vercel.app/openapi.json | jq '.paths | keys'   # inclui /kb/list, /kb/file, /kb/upload
```

Uma pergunta real no chat devolve `tool_steps` e a seção `Fontes:`; se a resposta vier vazia ou com erro de conexão, falta variável de ambiente (ou o deploy não foi refeito depois do sync).

## Scrape manual (`scrape-csa.yml`)

O workflow agora é **manual** (`workflow_dispatch`), sem agendamento e **sem commit**: roda `scripts/scrape_portal.py` via `uv sync --frozen`, grava `knowledge/raw/` no runner e publica a saída como artifact (`knowledge-raw`). Quem decide o que entra na base é o time, pelo upload (`POST /kb/upload`).

## Caminho manual

```bash
make deploy-env        # scripts/sync-vercel-env.sh production
make deploy-api        # raiz do repo: npx vercel deploy --prod --yes
make deploy-frontend   # frontend/: npx vercel deploy --prod --yes
make deploy-staging    # par de staging: chat-csa-api-preview + chat-csa-web-preview
```

Pré-requisito: `npx vercel link` uma vez em cada diretório (raiz e `frontend/`) — na Vercel, sem os tokens project-scoped do CI. Os alvos de staging já passam `--project`/`--scope` e funcionam sem link.

Enquanto os secrets `VERCEL_TOKEN_API_PREVIEW`/`VERCEL_TOKEN_FRONTEND_PREVIEW` não existirem, o CI **pula** o deploy de staging (aviso no run) — `make deploy-staging` publica o par com a sua sessão local, sem token nenhum.

## Alternativa: Docker

O `Dockerfile` da raiz gera uma imagem única do backend (porta 8000, `HEALTHCHECK` em `/health`, `AGENT_CONFIG_DIR=.consumer`) e `docker compose up` sobe consumer e frontend. É o caminho para hospedagem própria/single-host, não o usado na Vercel — os detalhes de variáveis estão em [configuracao.md](./configuracao.md).

## Limitações do ambiente serverless

- O `auth_store` é em memória: em cold start ou múltiplas instâncias da função, usuários e tokens resetam — inclusive os que protegem `/kb/upload`.
- O cache da base (TTL padrão 60s) vive na memória de cada instância; uploads aparecem na leitura após o TTL ou em uma nova instância.
- O filesystem da função é somente leitura e efêmero: nada da base é gravado em disco; o backend github não persiste arquivos localmente.
- O scraper é manual e roda no GitHub Actions (não roda na Vercel).

## Fontes

- `.github/workflows/deploy.yml`, `.github/workflows/env-sync.yml`, `.github/workflows/scrape-csa.yml`
- `.vercel/project.json`, `frontend/.vercel/project.json`
- `frontend/.env.production`, `frontend/src/api/client.ts`
- `vercel.json`, `frontend/vercel.json`, `api/index.py`
- `scripts/sync-vercel-env.sh`, `scripts/scrape_portal.py`
- `Makefile` (alvos `deploy-*`), `Dockerfile`, `docker-compose.yml`
- `README.md` (seção "Deploy")
