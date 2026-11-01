# ADR-003: Simplificação da Arquitetura DevOps, CI/CD e Handover

**Data:** 2026-11-01
**Status:** Aceita
**Decisores:** Equipe Chat CSA

---

## 1. Contexto

A publicação do Chat CSA na Vercel é feita via GitHub Actions utilizando a CLI da Vercel (`npx vercel deploy`), motivada pela ausência de permissões administrativas no repositório GitHub para instalar a integração nativa (GitHub App).

Para prover ambientes estáveis de produção e staging, a arquitetura anterior estabeleceu:
- **4 projetos na Vercel:** `chat-csa-api`, `chat-csa-web`, `chat-csa-api-preview`, `chat-csa-web-preview`.
- **10+ secrets no GitHub:** tokens project-scoped e IDs separados por projeto e ambiente (`VERCEL_TOKEN_API`, `VERCEL_TOKEN_FRONTEND`, `VERCEL_TOKEN_API_PREVIEW`, `VERCEL_TOKEN_FRONTEND_PREVIEW`, `VERCEL_ORG_ID_*`, `VERCEL_PROJECT_ID_*`).
- **Sincronização manual/automatizada via script:** `scripts/sync-vercel-env.sh` e `.github/workflows/env-sync.yml` com chamadas REST diretas à API da Vercel.
- **Acoplamento no workflow `deploy.yml`:** validações estáticas misturadas ao deploy e ausência de execução dos testes automatizados (`pytest tests/`), deixando mais de 130 testes de integração e regras sem validação contínua.

Essa configuração gerava alta sobrecarga cognitiva, fragilidade na manutenção e impeditivos graves para o handover ao cliente institucional/universidade.

---

## 2. Decisão

Adotar uma topologia simplificada de **2 projetos na Vercel** com uso de **URLs determinísticas de branch**, reduzir os segredos no GitHub para **4 variáveis universais de deploy**, desacoplar o pipeline em `ci.yml` (validações completas) e `deploy.yml` (entrega contínua pura), e gerenciar as variáveis de runtime diretamente pelo painel da Vercel.

### 2.1 Projetos na Vercel e Mapeamento de Branches

A infraestrutura é consolidada em 2 projetos principais vinculados ao mesmo repositório:

| Projeto Vercel | Diretório Raiz | Entrada / Framework | URL de Produção (`main`) | URL de Preview (`development`) |
|---|---|---|---|---|
| `chat-csa-api` | `.` (raiz) | `api/index.py` (`@vercel/python`) | `https://chat-csa-api.vercel.app` | `https://chat-csa-api-git-development-<escopo>.vercel.app` |
| `chat-csa-web` | `frontend/` | Vite + React (SPA) | `https://chat-csa-web.vercel.app` | `https://chat-csa-web-git-development-<escopo>.vercel.app` |

#### Resolução de URLs por Ambiente:
- **Produção (`main`):** Deploy executado com flag `--prod`. Atualiza imediatamente os domínios canônicos de produção.
- **Preview Estável (`development`):** Deploy padrão (sem `--prod`). A Vercel atribui automaticamente a URL de branch fixa vinculada a `development`. Essa URL aponta continuamente para o build mais recente do branch de trabalho.
- **Pull Requests:** Deploy efêmero por commit (gerado automaticamente no workflow de CI/deploy ou inspecionado localmente), sem necessidade de projetos dedicados de staging.

---

### 2.2 Matriz de Variáveis de Ambiente na Vercel

As variáveis de ambiente de runtime são configuradas diretamente no painel da Vercel (*Project Settings → Environment Variables*), eliminando scripts customizados de sincronização (`sync-vercel-env.sh`).

#### A. Projeto Backend (`chat-csa-api`)

| Variável | Escopo / Ambientes | Descrição / Exemplo |
|---|---|---|
| `LLM_PROVIDER` | Production, Preview | Provedor de LLM (`ollama`, `openai`, `groq`) |
| `LLM_MODEL` | Production, Preview | Nome do modelo (ex.: `gpt-4o-mini`, `gemma4:31b-cloud`) |
| `OLLAMA_MODEL` | Production, Preview | Modelo Ollama quando provedor for Ollama |
| `OLLAMA_BASE_URL` | Production: `https://ollama.com`<br>Preview: URL do gateway | Base URL para conexão com Ollama |
| `OLLAMA_API_KEY` | Production, Preview | Chave de API de acesso ao Ollama remoto |
| `OPENAI_API_KEY` | Production, Preview | Chave de API OpenAI (se provider `openai`) |
| `KB_BACKEND` | Production, Preview: `github` | Backend da base de conhecimento remota |
| `KB_REPO` | Production, Preview | Repositório do bundle OKF (ex.: `davi/chat-csa`) |
| `KB_BRANCH` | Production, Preview: `data` | Branch de dados que hospeda o bundle |
| `KB_ROOT` | Production, Preview: `knowledge` | Diretório raiz da base no repositório |
| `KB_TOKEN` | Production, Preview | Token GitHub com permissão de leitura |
| `KB_WRITE_TOKEN` | Production, Preview | Token GitHub para endpoints de upload (`/kb/upload`) |
| `KB_CACHE_TTL` | Production: `300`, Preview: `60` | TTL de cache em segundos na memória |

#### B. Projeto Frontend (`chat-csa-web`)

| Variável | Ambiente Vercel | Valor Alvo | Observações |
|---|---|---|---|
| `VITE_CONSUMER_URL` | **Production** | `https://chat-csa-api.vercel.app` | Embutida no build do Vite para a branch `main` |
| `VITE_CONSUMER_URL` | **Preview** | `https://chat-csa-api-git-development-<escopo>.vercel.app` | Embutida no build de Preview para o branch `development` |

*Nota:* O cliente frontend preserva a capacidade de substituição dinâmica da URL via query parameter `?consumerUrl=https://...`, permitindo testes contra deployments específicos sem recompilação.

---

### 2.3 Segredos no Repositório GitHub

O conjunto de segredos no GitHub é reduzido a **4 variáveis universais**:

| Secret GitHub | Finalidade | Escopo de Acesso |
|---|---|---|
| `VERCEL_TOKEN` | Token de deploy pessoal ou de time | Permissão de deployment nos 2 projetos |
| `VERCEL_ORG_ID` | ID do time/organização proprietária | Compartilhado entre ambos os projetos |
| `VERCEL_PROJECT_ID_API` | ID do projeto `chat-csa-api` | Identificador único do backend |
| `VERCEL_PROJECT_ID_FRONTEND` | ID do projeto `chat-csa-web` | Identificador único do frontend |

---

### 2.4 Arquitetura da Pipeline (GitHub Actions)

Desacoplamento estrito em dois fluxos complementares:

1. **`ci.yml` (Integração Contínua):**
   - **Gatilho:** `pull_request` contra `main` e `development`; `push` em branches de feature/trabalho.
   - **Permissões:** `contents: read` (não requer nenhum secret da Vercel).
   - **Jobs:**
     - `frontend`: Executa `npm ci`, `npx oxlint src`, `npm run build`.
     - `backend`: Executa `uv sync --frozen --group dev`, `ruff check src`, `pytest tests/`.
2. **`deploy.yml` (Entrega Contínua):**
   - **Gatilho:** `push` em `main` e `development`.
   - **Jobs:**
     - Validação prévia de sucesso do CI.
     - Deploy do backend `chat-csa-api` na raiz.
     - Deploy do frontend `chat-csa-web` em `frontend/`.
     - Publicação do resumo de execução (Deploy Summary) no step summary do GitHub Actions.

---

## 3. Consequências

### Positivas
- **Redução de complexidade:** De 4 para 2 projetos na Vercel; de 10+ para 4 secrets no repositório.
- **Qualidade garantida:** A suíte com mais de 130 testes automatizados (`pytest`) passa a rodar em todas as PRs e branches de desenvolvimento.
- **Eliminação de scripts proprietários de sync:** As variáveis vivem nativamente na Vercel com auditoria e controle de acesso nativo.
- **Handover viável:** O cliente/professor precisa apenas provisionar 2 projetos e 4 segredos para transferir toda a esteira operacional.

### Negativas e Mitigações
- **Provedor de URLs de preview:** Previews dependem do padrão de URLs gerado pelo escopo da Vercel (`-git-development-<escopo>`).
  *Mitigação:* A URL de branch da Vercel é determinística e estável para a branch `development`.
- **Desativação de staging dedicado:** Ambientes legados de preview (`chat-csa-api-preview` e `chat-csa-web-preview`) devem ser arquivados após a confirmação da nova esteira.
