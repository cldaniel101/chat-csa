# Deploy

Este documento cobre como o Chat CSA é publicado na Vercel: os dois projetos oficiais, o pipeline do GitHub Actions que faz o deploy automático, o gerenciamento de variáveis de ambiente no painel da Vercel e como a base de conhecimento remota é alimentada. Há também o caminho manual e a alternativa via Docker.

## Resumo para não-devs

O sistema possui dois serviços publicados na Vercel: a **API** (backend Python/FastAPI que responde às perguntas e serve a base de conhecimento) e o **site do chat** (aplicação web em React com botão flutuante). Publicar uma nova versão é 100% automático:
- Quando código é enviado para a branch `development`, um robô de integração roda os testes automatizados e publica uma versão de **Preview** com URL fixa e determinística para testes e homologação.
- Quando o código é promovido para a branch principal (`main`), o robô publica a versão oficial de **Produção**.
- A base de conhecimento não vai embutida no código: ela vive num branch separado (`data`) e é atualizada pelo time via upload admin; o deploy não altera conteúdo.

---

## Projetos na Vercel

A topologia é enxuta e adota **2 projetos principais** na Vercel vinculados ao repositório ([ADR-003](./adr/003-simplificacao-arquitetura-devops.md)):

| Projeto | Diretório no Repo | Entrada / Framework | URL de Produção (`main`) | URL de Preview (`development`) |
|---|---|---|---|---|
| `chat-csa-api` | `.` (raiz do repo) | `api/index.py` (`@vercel/python`) | `https://chat-csa-api.vercel.app` | `https://chat-csa-api-development.vercel.app` |
| `chat-csa-web` | `frontend/` | SPA Vite + React | `https://chat-csa-web.vercel.app` | `https://chat-csa-web-development.vercel.app` |

### Resolução de URLs e Ambientes
- **Produção (`main`):** Publicado com flag `--prod`. A Vercel promove imediatamente as URLs canônicas de produção.
- **Preview Estável (`development`):** Publicado na esteira de deploy e associado automaticamente ao alias estável e limpo (`chat-csa-*-development.vercel.app`). Essa URL é permanente e atualizada a cada push em `development`, dispensando projetos dedicados de staging e sufixos de time.
- **Configuração do Frontend (`VITE_CONSUMER_URL`):** O frontend é compilado no build com a URL da API do seu respectivo ambiente. No ambiente de Preview do projeto `chat-csa-web`, a variável `VITE_CONSUMER_URL` aponta para a URL estável da API de preview (`https://chat-csa-api-development.vercel.app`). Para homologação pontual de PRs ou deploys efêmeros, o frontend aceita o query parameter `?consumerUrl=https://...`.

### Configurações de Build na Vercel
- O `vercel.json` da raiz empacota `src/chat_csa/**` e `.consumer/**` e reescreve as rotas para `api/index.py`. O `api/index.py` adiciona `src/` ao `sys.path`, define `AGENT_CONFIG_DIR=.consumer` e expõe a aplicação FastAPI.
- O `frontend/vercel.json` aplica o rewrite de SPA direcionando requisições para `index.html`.

---

## Escopo e Propriedade

Os projetos pertencem ao escopo do time na Vercel (identificado por `VERCEL_ORG_ID`), garantindo continuidade institucional independentemente de contas pessoais.

Para gerenciar o deploy a partir do GitHub Actions são necessários **5 segredos**. Cada projeto usa um token **project-scoped** (`vcp_…`), restrito a um único projeto da Vercel — o CI não precisa de um token com acesso a todos os projetos do time:

| Secret (GitHub) | Descrição |
|---|---|
| `VERCEL_TOKEN_API` | Token project-scoped do projeto `chat-csa-api` |
| `VERCEL_TOKEN_FRONTEND` | Token project-scoped do projeto `chat-csa-web` |
| `VERCEL_ORG_ID` | ID do time proprietário dos projetos |
| `VERCEL_PROJECT_ID_API` | ID do projeto `chat-csa-api` |
| `VERCEL_PROJECT_ID_FRONTEND` | ID do projeto `chat-csa-web` |

O workflow resolve o token por job com `secrets[matrix.token_secret] || secrets.VERCEL_TOKEN`: quando `VERCEL_TOKEN_API`/`VERCEL_TOKEN_FRONTEND` existem, eles vencem. O `VERCEL_TOKEN` (token de time, aceito pelos dois projetos) permanece apenas como compatibilidade opcional e **não** está cadastrado. Decisão registrada na [ADR-004](./adr/004-tokens-deploy-project-scoped.md).

> **Token da Vercel é write-only:** o valor aparece uma única vez, na criação, e não há como recuperá-lo depois. "Renovar" significa sempre criar outro token e substituir o secret — não existe copiar o valor de um token existente.

---

## Pipelines do GitHub Actions

A esteira de integração e entrega contínua é dividida em dois fluxos complementares:

### 1. Integração Contínua (`.github/workflows/ci.yml`)
- **Disparo:** Pull requests contra `main` e `development`; pushes em branches de feature/trabalho (`feat/**`, `fix/**`, `chore/**`, etc.).
- **Permissões:** `contents: read` (não acessa segredos da Vercel).
- **Etapas em Paralelo:**
  - **Backend:** Configuração do Python 3.11 via `uv`, instalação congelada das dependências com grupo de testes (`uv sync --frozen --group dev`), linting com `ruff check src` e execução de mais de 140 testes automatizados com `pytest tests/`.
  - **Frontend:** Instalação limpa das dependências (`npm ci`), lint com `oxlint` e compilação completa com checagem de tipos (`npm run build`).

### 2. Entrega Contínua (`.github/workflows/deploy.yml`)
- **Disparo:** Pushes nas branches de publicação (`main` e `development`).
- **Comportamento:**
  - `main`: Executa deploy com a flag `--prod`, atualizando a produção.
  - `development`: Executa deploy sem a flag `--prod`, atualizando a URL estável de preview de branch.
  - A URL estável de preview é aplicada pela API da Vercel (`POST /v2/deployments/{id}/aliases`), não por `vercel alias set`: a CLI consulta `/v2/user`, que token project-scoped não acessa (`Error: User not found.`). O passo valida o retorno e reporta falha como `::warning::` no log, em vez de engolir o erro.
  - Publica no Step Summary do run um resumo legível com os links de acesso aos deploys.

---

## Dependências de Runtime: `pyproject.toml` × `api/requirements.txt`

A Vercel instala **apenas** `api/requirements.txt` (declarado no `builds` de `vercel.json`), enquanto o CI e o ambiente local usam `uv sync` a partir do `pyproject.toml`. As duas listas precisam caminhar juntas:

- toda dependência nova de runtime deve ser adicionada **nos dois arquivos**;
- se ela entrar só no `pyproject.toml`, o CI fica verde e a função quebra em produção com `FUNCTION_INVOCATION_FAILED` (HTTP 500 em todas as rotas);
- caso real: `cryptography`, usada por `src/chat_csa/unanswered.py`, faltava em `api/requirements.txt` e derrubou todas as rotas da API até ser adicionada.

---

## Variáveis de Ambiente de Runtime

Diferente da arquitetura antiga, variáveis de runtime do backend (`LLM_*`, `KB_*`) e do frontend (`VITE_CONSUMER_URL`) **não são sincronizadas por scripts** e não vivem nos secrets do GitHub Actions. Elas são configuradas diretamente no painel da Vercel:

1. Acesse o projeto na Vercel → **Settings** → **Environment Variables**.
2. Cadastre as variáveis selecionando os ambientes apropriados (**Production** e **Preview**).

### Variáveis da API (`chat-csa-api`)
- **Modelos e Provedores:** `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`.
- **Base de Conhecimento:** `KB_BACKEND=github`, `KB_REPO=cldaniel101/chat-csa`, `KB_BRANCH=data`, `KB_ROOT` vazio (o `index.md` está na raiz do branch), `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL`.
- **Painel administrativo:** `CHAT_CSA_ADMIN_USERNAME`, `CHAT_CSA_ADMIN_PASSWORD_HASH`, `CHAT_CSA_AUTH_SECRET`, `CHAT_CSA_AUTH_SESSION_TTL` e `CHAT_CSA_CORS_ORIGINS`. Gere o hash com `uv run python scripts/hash_admin_password.py`; não use prefixo `VITE_` para credenciais.
- **Perguntas sem resposta:** `CHAT_CSA_UNANSWERED_SECRET` (opcional, mínimo de 32 bytes). Sem ela, o módulo usa `CHAT_CSA_AUTH_SECRET` como chave.
- `CHAT_CSA_CORS_ORIGINS` aceita lista separada por vírgula e deve ser definida **por ambiente**: em Preview, a URL estável do frontend de preview; em Production, o domínio de produção. Origens fora da lista recebem `400` no preflight.

### Variáveis do Frontend (`chat-csa-web`)
- **Production:** `VITE_CONSUMER_URL=https://chat-csa-api.vercel.app`
- **Preview:** `VITE_CONSUMER_URL=https://chat-csa-api-development.vercel.app`

---

## Verificação Pós-Deploy

Para confirmar a saúde da API em qualquer ambiente:

```bash
# Healthcheck simples:
curl -s https://chat-csa-api.vercel.app/health
# {"status":"ok","config_dir":"/var/task/.consumer","config_exists":true}

# Verificação do OpenAPI:
curl -s https://chat-csa-api.vercel.app/openapi.json | jq '.paths | keys'
```

> Alterar variáveis de ambiente na Vercel **não** afeta deployments já criados: é preciso redeployar (`vercel redeploy` ou novo push) para o runtime ler os novos valores.

Para validar o preview sem credenciais:

```bash
uv run python scripts/validate_preview.py
```

O comando verifica healthcheck, carregamento do frontend, bloqueio sem token,
login inválido e CORS. Para incluir login real, TTL e recarga do painel, defina
temporariamente `CHAT_CSA_SMOKE_ADMIN_PASSWORD` no terminal e passe somente o
nome de usuário com `--admin-username`. A senha e o token nunca são impressos,
gravados ou enviados ao frontend.

---

## Deploy Manual (Alternativa ao CI)

Com as credenciais da Vercel autenticadas localmente (`npx vercel login`):

```bash
# Produção (main)
make deploy-api             # Deploy do backend na raiz
make deploy-frontend        # Deploy do frontend em frontend/

# Preview (development)
make deploy-preview-api     # Preview do backend
make deploy-preview-frontend # Preview do frontend
```

---

## Alternativa: Docker

O `Dockerfile` da raiz gera uma imagem containerizada única do backend e `docker compose up` sobe backend e frontend juntos. Consulte [configuracao.md](./configuracao.md) para detalhes de execução local e variáveis de ambiente em containers.

## Fontes

- `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `.github/workflows/scrape-csa.yml`
- `docs/adr/003-simplificacao-arquitetura-devops.md`
- `docs/inventario-descontinuacao-devops.md`
- `vercel.json`, `frontend/vercel.json`, `api/index.py`
- `Makefile`, `Dockerfile`, `docker-compose.yml`
