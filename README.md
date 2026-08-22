# Chat CSA — Assistente Inteligente para o SISU/UEFS

O **Chat CSA** é um projeto de extensão da **Universidade Estadual de Feira de Santana (UEFS)** que tem como objetivo desenvolver um assistente baseado em Inteligência Artificial para auxiliar estudantes e candidatos durante o processo seletivo do **SISU na UEFS**.

A proposta é disponibilizar uma interface conversacional capaz de responder, de maneira simples e acessível, dúvidas relacionadas ao processo seletivo, utilizando como principal fonte de informação os conteúdos oficiais publicados pela **Coordenação de Seleção e Admissão (CSA/UEFS)**.

## 🎯 Objetivo

Facilitar o acesso às informações do SISU/UEFS por meio de um assistente virtual capaz de interpretar perguntas em linguagem natural e fornecer respostas fundamentadas nas informações oficiais divulgadas pela universidade.

O projeto busca reduzir dificuldades como:

* dispersão de informações entre páginas, editais e comunicados;
* dificuldade de interpretação de documentos oficiais;
* repetição de dúvidas frequentes entre candidatos;
* necessidade de localizar rapidamente prazos, documentos e procedimentos;
* dificuldade de navegação pelo portal da CSA.

## 💡 Motivação

Durante os processos seletivos, candidatos frequentemente possuem dúvidas sobre assuntos como:

* inscrições;
* classificação;
* chamadas;
* lista de espera;
* matrícula;
* documentação;
* cotas e modalidades de concorrência;
* cronogramas;
* resultados;
* procedimentos após a convocação.

Embora essas informações estejam disponíveis nos canais oficiais da UEFS, nem sempre é simples localizar ou interpretar rapidamente o conteúdo desejado.

O Chat CSA pretende funcionar como uma **camada de acesso conversacional às informações oficiais**, permitindo que o candidato faça perguntas diretamente ao sistema.

Exemplo:

> **Usuário:** Quais documentos preciso apresentar para realizar minha matrícula?

> **Chat CSA:** consulta as informações oficiais disponíveis sobre o processo seletivo e apresenta uma resposta objetiva, indicando a fonte utilizada.

## 🔎 Fonte das informações

As respostas do sistema devem ser fundamentadas prioritariamente nas informações oficiais disponibilizadas pela **CSA/UEFS**.

Portal oficial:

https://csa.uefs.br/

Página do processo SISU utilizada como referência inicial:

https://csa.uefs.br/index.php/sisu261/inicial

A utilização de fontes oficiais é um dos princípios centrais do projeto, buscando reduzir o risco de informações incorretas ou desatualizadas.

## 🤖 Funcionamento proposto

De forma geral, o sistema deverá seguir o seguinte fluxo:

1. O candidato envia uma pergunta em linguagem natural.
2. O sistema interpreta a dúvida apresentada.
3. O assistente busca informações relevantes nas fontes oficiais do SISU/UEFS.
4. O conteúdo encontrado é utilizado como contexto para o modelo de Inteligência Artificial.
5. Uma resposta clara e objetiva é apresentada ao usuário.
6. Sempre que possível, a origem da informação é indicada para permitir sua verificação.

## ✅ Requisitos importantes

O assistente deverá priorizar:

* respostas baseadas em fontes oficiais;
* indicação das fontes utilizadas;
* linguagem simples e acessível;
* respostas objetivas;
* identificação de situações em que não existam informações suficientes;
* prevenção de respostas inventadas ou não verificadas;
* atualização das informações conforme novos documentos sejam publicados pela CSA.

O sistema **não substitui os editais, comunicados ou orientações oficiais da UEFS**. Em situações de divergência, sempre prevalecerá a documentação publicada oficialmente pela universidade.

## 🧠 Inteligência Artificial e recuperação de informações

Uma das possibilidades para implementação do projeto é utilizar uma arquitetura baseada em **RAG — Retrieval-Augmented Generation (Geração Aumentada por Recuperação)**.

Nesse modelo, a IA não depende apenas do conhecimento previamente adquirido pelo modelo. Antes de gerar uma resposta, o sistema recupera informações relevantes a partir da base documental do SISU/UEFS.

Fluxo simplificado:

```text
Pergunta do usuário
        ↓
Interpretação da pergunta
        ↓
Busca nas informações oficiais
        ↓
Recuperação dos conteúdos relevantes
        ↓
Modelo de linguagem
        ↓
Resposta fundamentada
        ↓
Indicação da fonte
```

Essa abordagem pode contribuir para aumentar a confiabilidade e a rastreabilidade das respostas.

## 📋 Escopo inicial

O projeto deverá contemplar dúvidas relacionadas ao processo SISU/UEFS, incluindo, entre outros:

* cronograma;
* inscrição;
* classificação;
* modalidades de concorrência;
* ações afirmativas e cotas;
* chamadas;
* lista de espera;
* matrícula;
* documentação;
* resultados;
* procedimentos administrativos relacionados ao processo seletivo.

Assuntos que não estejam documentados nas fontes oficiais utilizadas pelo sistema deverão ser tratados com cautela, evitando inferências apresentadas como fatos.

## 🛠️ Etapas do projeto

O desenvolvimento pode ser dividido nas seguintes etapas:

### 1. Diagnóstico

* identificação das principais dificuldades enfrentadas pelos candidatos;
* levantamento das dúvidas mais frequentes;
* análise do portal da CSA e dos documentos publicados;
* definição dos requisitos do assistente.

### 2. Coleta e organização dos dados

* identificação das páginas relevantes;
* coleta de editais, comunicados e documentos;
* organização e limpeza dos conteúdos;
* estruturação da base de conhecimento.

### 3. Desenvolvimento

* implementação do mecanismo de recuperação das informações;
* integração com modelo de linguagem;
* desenvolvimento da interface de chat;
* implementação de referências às fontes consultadas.

### 4. Testes

* criação de perguntas representativas;
* comparação das respostas com documentos oficiais;
* análise de respostas incorretas ou incompletas;
* ajustes no mecanismo de recuperação e nos prompts.

### 5. Interação com a comunidade

* disponibilização do protótipo para estudantes;
* coleta de feedback;
* identificação de dúvidas não contempladas;
* avaliação da clareza e utilidade das respostas.

### 6. Avaliação e evolução

* análise dos resultados obtidos;
* documentação das limitações;
* correção de problemas identificados;
* definição de melhorias futuras.

## 📊 Avaliação do projeto

Além da implementação técnica, o projeto considera aspectos importantes de uma atividade de extensão universitária, como:

* diagnóstico da demanda;
* planejamento;
* organização da equipe;
* execução das atividades;
* qualidade técnica;
* colaboração;
* interação com a comunidade;
* registro das atividades;
* qualidade do produto entregue;
* reflexão crítica sobre limitações e possibilidades de evolução.

## 👥 Equipe

Projeto de Extensão — Universidade Estadual de Feira de Santana (UEFS)

**Orientador:**
Prof. João B. Rocha

**Equipe:**
* Cláudio Daniel Figueredo Peruna
* Davi Macêdo Gomes
* Paulo Gabriel da Rocha Costa Silva
  
## 📚 Documentação

Durante o desenvolvimento, este repositório também poderá concentrar registros relacionados a:

```text
docs/
├── requisitos/
├── reunioes/
├── pesquisas/
├── testes/
├── feedbacks/
├── arquitetura/
└── relatorios/
```

Esse registro permitirá acompanhar não apenas o código desenvolvido, mas também as decisões, experimentos, resultados e evolução do projeto.

## 🤖 Agents — LangChain + Skills (`.ingester` / `.consumer`)

This repo ships a **simple LangChain agent** with a filesystem skill system that mirrors `.agents/` — but split into two isolated configs:

| Agent | Config dir | Purpose |
|-------|------------|---------|
| **Ingester** | `.ingester/` | Crawl → normalize → curate CSA sources into OKF bundle + BM25 index |
| **Consumer** | `.consumer/` | Answer questions via retrieval (extractive, cited) |

Each dir is a standalone *AGENTS home*:
```
.ingester/
  AGENTS.md           # project instructions for this agent
  skills/
    csa-ingest/
      SKILL.md        # skill description (any .md folder counts)
.consumer/
  AGENTS.md
  skills/
    csa-query/
      SKILL.md
```
Any `.md` skill you drop there is concatenated into the system prompt (hot-reloaded every request). Add a skill by creating a folder:
```bash
mkdir -p .ingester/skills/my-skill
cat > .ingester/skills/my-skill/SKILL.md <<'EOF'
---
name: my-skill
description: does X
allowed-tools: read write edit bash
---
# My skill — instructions for the agent
EOF
```

**Tools available to every skill:** `read(path)`, `write(path, content)`, `edit(path, oldText, newText)`, `bash(command)`.

**API:** OpenAI-compatible (`POST /v1/chat/completions`, `GET /v1/models`) **+** Ollama-native shim (`POST /api/chat`, `GET /api/tags`). Works with the OpenAI SDK, `curl`, and Ollama clients pointing at `http://localhost:8001/v1`.

### Quickstart (uv)

```bash
cp .env.example .env   # .env has BOTH agents: INGESTER_* (.ingester :8001) + CONSUMER_* (.consumer :8002)
# edit LLM_PROVIDER / OLLAMA_BASE_URL or OPENAI_API_KEY — shared defaults apply to both
# each agent also supports per-agent overrides: INGESTER_LLM_PROVIDER, CONSUMER_LLM_MODEL, etc.
uv sync --group dev
uv run chat-csa print-prompt --config-dir .ingester   # debug prompt
make run-ingester   # :8001  (uses INGESTER_CONFIG_DIR/INGESTER_PORT from .env, or --config-dir flag)
make run-consumer   # :8002  (uses CONSUMER_CONFIG_DIR/CONSUMER_PORT)
make run-both       # both side-by-side via -j2
# In another shell — OpenAI SDK example
curl http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"quais documentos para matrícula?"}]}'
# Ollama shim
curl http://localhost:8001/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"oi"}]}'
```

Single agent (override per-run):
```bash
LLM_PROVIDER=ollama LLM_MODEL=llama3.2 uv run chat-csa serve --config-dir .consumer --port 8002
LLM_PROVIDER=openai OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini uv run chat-csa serve --config-dir .consumer --port 8002
```

Ollama local model (default):
```bash
ollama pull llama3.2
ollama serve  # default http://localhost:11434
# then make run-both reads OLLAMA_BASE_URL from .env
```

### Docker (no uv needed)

```bash
docker build -t chat-csa .
# single

docker run --rm -p 8001:8000 -e AGENT_CONFIG_DIR=.ingester -e LLM_PROVIDER=ollama -e OLLAMA_BASE_URL=http://host.docker.internal:11434 chat-csa
# both agents (reads INGESTER_*/CONSUMER_* from .env — see .env.example)
make docker-build
docker compose up   # ingester :${INGESTER_PORT:-8001} + consumer :${CONSUMER_PORT:-8002} + frontend :${FRONTEND_PORT:-5173}
# per-agent overrides also work:
# INGESTER_LLM_PROVIDER=openai INGESTER_OPENAI_API_KEY=sk-... docker compose up
# frontend respects VITE_INGESTER_URL / VITE_CONSUMER_URL at build time
```

> **Why two vars?** `AGENT_CONFIG_DIR` is per-process (one agent = one dir + one port). `.env.example` therefore ships **both** `INGESTER_CONFIG_DIR` + `CONSUMER_CONFIG_DIR` (and `INGESTER_PORT`/`CONSUMER_PORT`) plus a fallback `AGENT_CONFIG_DIR`/`PORT` for single-agent mode. `Makefile` and `docker-compose.yml` read the `INGESTER_*`/`CONSUMER_*` set; the server itself still honors `AGENT_CONFIG_DIR` per instance.

### React Chat (frontend/)

Vite + React + React Router chat that talks to **both** agents via their OpenAI-compatible endpoints.

```bash
cp frontend/.env.example frontend/.env   # VITE_INGESTER_URL=http://localhost:8001 etc.
make frontend-install
make frontend-dev      # http://localhost:5173
make frontend-build    # production build -> frontend/dist (served by nginx in docker)
```

- **Agent switcher**: sidebar toggle between Consumer (public) and Ingester (protected).
- **Consumer**: open chat, no login.
- **Ingester**: requires login (`admin / sudo123`). Login hits `POST /auth/login` on the ingester API and stores a bearer token.
- **Admin CRUD**: `/admin` page (protected) — list/add/edit/delete users via `GET/POST/PUT/DELETE /admin/users` on the ingester API. In-memory store, seeded with `admin/sudo123`.
- Env: `VITE_INGESTER_URL` / `VITE_CONSUMER_URL` (defaults 8001/8002). With Docker Compose the frontend is at `http://localhost:5173` and proxies to both backends.

### Makefile DX

| Target | What it does |
|--------|---------------|
| `make install` | `uv sync` |
| `make dev` | installs dev group |
| `make run-ingester` | ingester on `$INGESTER_PORT` (`INGESTER_CONFIG_DIR`) |
| `make run-consumer` | consumer on `$CONSUMER_PORT` (`CONSUMER_CONFIG_DIR`) |
| `make run-both` | both with `-j2` (respects all `INGESTER_*`/`CONSUMER_*` overrides) |
| `make prompt-ingester` / `prompt-consumer` | print composed system prompt (AGENTS.md + skills) |
| `make frontend-install` / `frontend-dev` / `frontend-build` | React app |
| `make lint` / `format` / `test` | ruff + pytest |
| `make docker-build` / `docker-run*` / `docker-run-both` | container flow |

See `docs/proposta-okf-bm25.md` for the OKF+BM25 architecture.

## 🚧 Status

**Em desenvolvimento.**

As funcionalidades, arquitetura e base de conhecimento estão sendo desenvolvidas e avaliadas durante a execução do projeto de extensão.

## ⚠️ Aviso

O Chat CSA é um projeto acadêmico e experimental.

As respostas produzidas pelo assistente têm caráter informativo e devem ser verificadas nos canais oficiais da Universidade Estadual de Feira de Santana.

Em caso de divergência, **os editais, resoluções, comunicados e demais publicações oficiais da CSA/UEFS têm precedência sobre qualquer resposta apresentada pelo sistema.**
