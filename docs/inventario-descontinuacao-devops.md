# Inventário de Descontinuação e Limpeza DevOps

Este documento audita e inventaria os recursos legados (projetos na Vercel e segredos no GitHub Actions) tornados obsoletos pela simplificação da arquitetura DevOps ([ADR-003](./adr/003-simplificacao-arquitetura-devops.md)).

---

## 1. Projetos Vercel para Descomissionamento

Com a adoção de URLs de branch determinísticas da Vercel (`-git-development-...`), os projetos dedicados de staging deixam de ser necessários.

| Projeto Vercel Legado | Diretório | Função Anterior | Ação Recomendada |
|---|---|---|---|
| `chat-csa-api-preview` | `.` (raiz) | Staging do backend publicado com `--prod` | **Excluir** no painel da Vercel após validação de `development` |
| `chat-csa-web-preview` | `frontend/` | Staging do frontend publicado com `--prod` | **Excluir** no painel da Vercel após validação de `development` |

> **Nota:** Os projetos ativos continuam sendo apenas `chat-csa-api` e `chat-csa-web`.

---

## 2. Segredos do GitHub Actions (Auditoria)

### 2.1 Segredos a Excluir do GitHub (`Settings → Secrets and variables → Actions`)

#### A. Segredos de Deploy da Vercel Legados (Substituídos pelos 4 unificados)
1. `VERCEL_TOKEN_API` — *Substituído pelo unificado `VERCEL_TOKEN`*
2. `VERCEL_TOKEN_FRONTEND` — *Substituído pelo unificado `VERCEL_TOKEN`*
3. `VERCEL_TOKEN_API_PREVIEW` — *Obsoleto (projeto staging)*
4. `VERCEL_TOKEN_FRONTEND_PREVIEW` — *Obsoleto (projeto staging)*
5. `VERCEL_ORG_ID_API` — *Substituído pelo unificado `VERCEL_ORG_ID`*
6. `VERCEL_ORG_ID_FRONTEND` — *Substituído pelo unificado `VERCEL_ORG_ID`*
7. `VERCEL_PROJECT_ID_API_PREVIEW` — *Obsoleto (projeto staging)*
8. `VERCEL_PROJECT_ID_FRONTEND_PREVIEW` — *Obsoleto (projeto staging)*

#### B. Segredos de Runtime Sincronizados via GitHub Actions (Agora Nativos na Vercel)
Estes segredos eram consumidos exclusivamente pelo workflow `env-sync.yml` (agora removido). Devem ser configurados nas **Environment Variables** do projeto `chat-csa-api` na Vercel e depois removidos do GitHub para evitar duplicidade e vazamentos:
1. `LLM_PROVIDER`
2. `LLM_MODEL`
3. `OLLAMA_MODEL`
4. `OLLAMA_BASE_URL`
5. `OLLAMA_API_KEY`
6. `OPENAI_API_KEY` (se aplicável)
7. `KB_BACKEND`
8. `KB_REPO`
9. `KB_BRANCH`
10. `KB_ROOT`
11. `KB_TOKEN`
12. `KB_WRITE_TOKEN`
13. `KB_CACHE_TTL`

---

### 2.2 Segredos Ativos e Obrigatórios no GitHub

Apenas **4 segredos** devem permanecer configurados no GitHub:

| Secret | Valor Esperado |
|---|---|
| `VERCEL_TOKEN` | Token de deploy pessoal ou de time com permissão nos projetos |
| `VERCEL_ORG_ID` | ID do time proprietário dos projetos na Vercel |
| `VERCEL_PROJECT_ID_API` | ID do projeto `chat-csa-api` |
| `VERCEL_PROJECT_ID_FRONTEND` | ID do projeto `chat-csa-web` |

---

## 3. Roteiro Seguro de Descomissionamento

1. **Configurar os 4 Segredos Novos no GitHub:**
   - Adicionar `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID_API`, `VERCEL_PROJECT_ID_FRONTEND`.
2. **Validar o Deploy do Branch `development`:**
   - Disparar o workflow `deploy.yml` em `development` e confirmar que `chat-csa-api` e `chat-csa-web` publicam na URL estável de preview.
3. **Validar o Deploy do Branch `main`:**
   - Mesclar em `main` e confirmar que a produção continua saudável em `chat-csa-api.vercel.app` e `chat-csa-web.vercel.app`.
4. **Remover os Segredos Legados do GitHub:**
   - Excluir os 8 segredos de deploy legados e os segredos de runtime obsoletos no repositório.
5. **Arquivar/Excluir Projetos de Staging na Vercel:**
   - No painel da Vercel: acessar `chat-csa-api-preview` → *Settings → Advanced → Delete Project*.
   - Acessar `chat-csa-web-preview` → *Settings → Advanced → Delete Project*.
