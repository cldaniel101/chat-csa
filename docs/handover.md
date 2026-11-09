# Guia de Handover: Deploy e Infraestrutura Chat CSA

Este documento serve como guia definitivo para a equipe receptora, professor ou cliente institucional assumir e operar a infraestrutura de publicação contínua (CI/CD) do **Chat CSA**.

A arquitetura foi simplificada conforme a [ADR-003](./adr/003-simplificacao-arquitetura-devops.md) para operar com apenas **2 projetos na Vercel**, 5 segredos de deploy (um token project-scoped por projeto, conforme a [ADR-004](./adr/004-tokens-deploy-project-scoped.md)) e 3 segredos do alerta de atualização no GitHub.

---

## Checklist de Handover (Passo a Passo em 5 Etapas)

### 1. Criar os Projetos na Vercel
1. Acesse [vercel.com](https://vercel.com) com a conta institucional ou crie um time (ex.: `csa-uefs`).
2. **Projeto da API (Backend):**
   - Clique em **Add New... → Project** e selecione o repositório do Chat CSA.
   - Nome do projeto: `chat-csa-api`
   - Framework Preset: **Other** (ou Python)
   - Root Directory: `.` (raiz do repositório)
   - Clique em **Deploy** ou salve a configuração.
3. **Projeto do Site (Frontend):**
   - Adicione outro projeto no mesmo repositório.
   - Nome do projeto: `chat-csa-web`
   - Framework Preset: **Vite**
   - Root Directory: `frontend`
   - Clique em **Deploy** ou salve a configuração.

---

### 2. Cadastrar as Variáveis de Ambiente na Vercel
No painel da Vercel, acesse as configurações de cada projeto (*Settings → Environment Variables*):

#### A. No projeto `chat-csa-api`:
Cadastre para os ambientes **Production** e **Preview**:
- `LLM_PROVIDER`: Provedor do modelo (`ollama`, `openai`, `groq`, etc.)
- `LLM_MODEL`: Nome do modelo (ex.: `gpt-4o-mini`, `gemma4:31b-cloud`)
- `OLLAMA_BASE_URL` e `OLLAMA_API_KEY` (se usar Ollama remoto)
- `OPENAI_API_KEY` (se usar OpenAI)
- `KB_BACKEND`: `github`
- `KB_REPO`: Repositório da base (ex.: `seu-usuario-ou-org/chat-csa`)
- `KB_BRANCH`: `data`
- `KB_ROOT`: vazio, pois `index.md` está diretamente na raiz do branch `data`
- `KB_TOKEN`: Personal Access Token do GitHub com permissão `contents:read`
- `KB_WRITE_TOKEN`: Token com permissão de escrita para o endpoint `/kb/upload` (pode ser o mesmo `KB_TOKEN`)
- `KB_CACHE_TTL`: `300` (em segundos)
- `CHAT_CSA_ADMIN_USERNAME`: usuário inicial do painel (não use credencial de demonstração)
- `CHAT_CSA_ADMIN_PASSWORD_HASH`: hash gerado localmente com `uv run python scripts/hash_admin_password.py` (o código exige senha com **no mínimo 12 caracteres**)
- `CHAT_CSA_AUTH_SECRET`: segredo aleatório de sessão com no mínimo 32 bytes
- `CHAT_CSA_AUTH_SESSION_TTL`: `28800` (8 horas)
- `CHAT_CSA_CORS_ORIGINS`: domínio do frontend do respectivo ambiente, sem barra final
- `CHAT_CSA_UNANSWERED_SECRET` (opcional): chave das perguntas sem resposta, mínimo de 32 bytes; sem ela o módulo usa `CHAT_CSA_AUTH_SECRET`

Exemplo de `CHAT_CSA_CORS_ORIGINS` por ambiente: `https://chat-csa-web-development.vercel.app` em Preview e `https://chat-csa-web.vercel.app` em Production. O valor é uma lista separada por vírgula; inclua a origem oficial do CSA quando o widget for integrado a ela.

As variáveis administrativas existem somente no projeto da API. Nunca crie equivalentes com prefixo `VITE_`.

#### B. No projeto `chat-csa-web`:
Cadastre as variáveis do Vite:
- **Ambiente Production:**
  - `VITE_CONSUMER_URL`: `https://chat-csa-api.vercel.app` (ou o domínio customizado de produção da API)
- **Ambiente Preview:**
  - `VITE_CONSUMER_URL`: `https://chat-csa-api-development.vercel.app` (URL limpa e estável de preview da API)

---

### 3. Gerar os Tokens de Deploy da Vercel
São **dois** tokens, um por projeto, para não conceder acesso a todos os projetos do time:
1. No painel da Vercel, acesse **Account Settings** → **Tokens**.
2. Clique em **Create Token**.
3. Token do backend: nome `chat-csa-github-actions-api`, restrito ao projeto `chat-csa-api`, com validade definida.
4. Token do frontend: nome `chat-csa-github-actions-web`, restrito ao projeto `chat-csa-web`.
5. Copie o valor de cada um no momento da criação.

> Token da Vercel é **write-only**: o valor aparece uma única vez e não há como recuperá-lo depois. "Renovar" significa criar outro e substituir o secret. Um token de escopo de time também funciona, no secret `VERCEL_TOKEN` (fallback opcional do workflow), mas passa a valer para todos os projetos do time.

---

### 4. Configurar os Segredos no Repositório GitHub
No repositório do GitHub, acesse **Settings** → **Secrets and variables** → **Actions**. Para o deploy, cadastre estes 5 segredos:

| Secret | Descrição / Onde Obter |
|---|---|
| `VERCEL_TOKEN_API` | Token project-scoped do projeto `chat-csa-api` (etapa 3) |
| `VERCEL_TOKEN_FRONTEND` | Token project-scoped do projeto `chat-csa-web` (etapa 3) |
| `VERCEL_ORG_ID` | O ID da conta ou time dono dos projetos na Vercel (*Team Settings → General → Team ID*) |
| `VERCEL_PROJECT_ID_API` | O ID do projeto `chat-csa-api` (*Project Settings → General → Project ID*) |
| `VERCEL_PROJECT_ID_FRONTEND` | O ID do projeto `chat-csa-web` (*Project Settings → General → Project ID*) |

Para o alerta do scrape, cadastre também como **repository secrets**:

| Secret | Descrição |
|---|---|
| `CHAT_CSA_EMAIL_API_URL` | Endpoint HTTPS da API de e-mail |
| `CHAT_CSA_EMAIL_API_TOKEN` | Token Bearer da API de e-mail |
| `CHAT_CSA_UPDATE_NOTIFICATION_TO` | Endereço que receberá os avisos de revisão |

Não coloque esses valores em variables, arquivos versionados ou chaves `VITE_*`. Opcionalmente, crie a repository variable pública `CHAT_CSA_ADMIN_PANEL_URL` para trocar o link do painel enviado no e-mail. Se o portal bloquear o runner hospedado pelo GitHub, configure também `SCRAPE_RUNNER` com o label de um runner Linux que alcance a rede da CSA.

---

### 5. Validação dos Ambientes
1. **Validação do Preview:**
   - Faça um push de teste na branch `development`.
   - Acompanhe a execução da aba **Actions**:
     - O workflow `CI` executará linters e a suíte com mais de 140 testes (`pytest`).
     - O workflow `Deploy` publicará a API e o Frontend na URL de preview de branch.
   - Acesse a URL de preview do frontend e faça uma pergunta para verificar a integração fim a fim.
2. **Validação da Produção:**
   - Abra um Pull Request de `development` para `main` e realize o merge.
   - O workflow `Deploy` publicará a versão final em produção (`--prod`).
   - Verifique a saúde em `https://chat-csa-api.vercel.app/health`.
3. **Validação do fluxo manual de atualização:**
   - Em **Actions → Scrape portal CSA**, execute **Run workflow**.
   - Na primeira execução sem referência anterior, todos os documentos coletados são classificados como novos. Nas seguintes, apenas corpos novos ou alterados geram aviso.
   - Confirme o recebimento do e-mail, abra o link `/admin`, baixe o artifact `knowledge-raw` na execução e revise o material.
   - Envie o documento para a seção correta. Reenviar o mesmo caminho substitui o conceito existente e atualiza os índices de forma atômica.
   - Execute novamente sem alterar a origem: o resumo deve indicar `written: 0` e nenhum e-mail deve ser enviado.
