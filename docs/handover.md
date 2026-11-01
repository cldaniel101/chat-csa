# Guia de Handover: Deploy e Infraestrutura Chat CSA

Este documento serve como guia definitivo para a equipe receptora, professor ou cliente institucional assumir e operar a infraestrutura de publicação contínua (CI/CD) do **Chat CSA**.

A arquitetura foi simplificada conforme a [ADR-003](./adr/003-simplificacao-arquitetura-devops.md) para operar com apenas **2 projetos na Vercel** e **4 segredos no GitHub**.

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
- `KB_ROOT`: `knowledge`
- `KB_TOKEN`: Personal Access Token do GitHub com permissão `contents:read`
- `KB_WRITE_TOKEN`: Token com permissão de escrita para o endpoint `/kb/upload` (pode ser o mesmo `KB_TOKEN`)
- `KB_CACHE_TTL`: `300` (em segundos)

#### B. No projeto `chat-csa-web`:
Cadastre as variáveis do Vite:
- **Ambiente Production:**
  - `VITE_CONSUMER_URL`: `https://chat-csa-api.vercel.app` (ou o domínio customizado de produção da API)
- **Ambiente Preview:**
  - `VITE_CONSUMER_URL`: `https://chat-csa-api-git-development-<seu-time>.vercel.app` (URL de branch estável de preview da API)

---

### 3. Gerar o Token de Deploy da Vercel
1. No painel da Vercel, acesse **Account Settings** (ou **Team Settings**) → **Tokens**.
2. Clique em **Create Token**.
3. Defina um nome descritivo (ex.: `github-actions-chat-csa`) e escopo adequado com permissão para realizar deployments.
4. Copie o valor gerado.

---

### 4. Configurar os 4 Segredos no Repositório GitHub
No repositório do GitHub, acesse **Settings** → **Secrets and variables** → **Actions** e cadastre exatamente estes 4 segredos:

| Secret | Descrição / Onde Obter |
|---|---|
| `VERCEL_TOKEN` | O token de deploy gerado na etapa 3 |
| `VERCEL_ORG_ID` | O ID da conta ou time dono dos projetos na Vercel (*Team Settings → General → Team ID*) |
| `VERCEL_PROJECT_ID_API` | O ID do projeto `chat-csa-api` (*Project Settings → General → Project ID*) |
| `VERCEL_PROJECT_ID_FRONTEND` | O ID do projeto `chat-csa-web` (*Project Settings → General → Project ID*) |

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
