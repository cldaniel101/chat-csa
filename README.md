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

## 🤖 Funcionamento

De forma geral, o sistema funciona da seguinte maneira:

1. O candidato envia uma pergunta em linguagem natural.
2. O agente **consumer** busca informações relevantes no bundle de conhecimento (OKF) curado a partir das fontes oficiais do SISU/UEFS e, se necessário, consulta o portal da CSA diretamente.
3. O conteúdo recuperado fundamenta uma resposta **extrativa**, com citações (URL + timestamp).
4. Se a informação não existir nas fontes oficiais, o sistema declara isso explicitamente em vez de inventar.
5. A resposta indica sempre a origem da informação para permitir sua verificação.

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

## 🧠 Arquitetura — Bundle OKF + recuperação determinística

O projeto **não utiliza RAG** (embeddings vetoriais + geração aumentada por recuperação). Em vez disso, adota uma abordagem **determinística e auditável**, baseada em um bundle de conhecimento curado no formato **OKF — Open Knowledge Format** e em recuperação determinística por consulta direta aos conceitos curados e ao portal da CSA quando necessário:

```text
Fontes oficiais da CSA/UEFS (portal csa.uefs.br)
        ↓  (agente ingester — crawl, normalização, curadoria)
Bundle de conhecimento OKF (conceitos versionados em Markdown)
        ↓  (recuperação determinística — consulta direta ao bundle e ao portal)
Agente consumer — resposta extrativa com citações
        ↓
Usuário (resposta verificável, com URL e timestamp)
```

Motivações principais dessa escolha:

* **Zero alucinação no caminho crítico**: as respostas são extrativas, extraídas verbatim de conceitos curados;
* **Auditabilidade**: cada frase é rastreável até uma fonte oficial;
* **Terminologia literal**: consultas sobre SISU são lexicais ("comprovante de cota racial", "lista de espera") — correspondência lexical supera busca semântica;
* **Custo e simplicidade**: sem banco vetorial nem API de embeddings — roda offline e barato.

O consumer responde consultando diretamente os conceitos do bundle e o portal via `web_csa_fetch`/`web_csa_search`.

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

## 📖 Base de Conhecimento (Knowledge)

A base de conhecimento do Chat CSA é um conjunto de arquivos Markdown curados no formato **OKF (Open Knowledge Format)**, organizados na pasta `knowledge/` na raiz do repositório. Ela é a **fonte única da verdade** usada pelo agente consumer para responder perguntas.

**Para obter a base funcional, basta clonar o repositório:**

```bash
git clone https://github.com/cldaniel101/chat-csa.git
# A pasta knowledge/ já vem incluída com os conceitos curados
```

Não é necessário executar scripts extras, downloads ou configurações adicionais para ter acesso à base mínima.

### Estrutura

```text
knowledge/
├── index.md                    # Índice raiz — categorias e convenções
├── log.md                      # Registro cronológico de alterações
├── editais/                    # Documentos normativos oficiais
├── cronogramas/                # Datas e prazos do processo seletivo
├── procedimentos/              # Passos para inscrição, matrícula, etc.
├── modalidades/                # Regras de concorrência e cotas
└── perguntas-frequentes/       # FAQs curadas a partir das fontes oficiais
```

### Convenções

- Cada conceito possui **frontmatter YAML** com `type`, `title`, `description`, `resource` (URL oficial), `tags` e `timestamp`.
- Índices (`index.md`) não possuem frontmatter — servem para navegação.
- Cross-links usam caminhos relativos dentro do bundle.
- Toda alteração é rastreada via Git (`git blame`, `git log`) e registrada em `knowledge/log.md`.

> **Decisão arquitetural:** A base é versionada diretamente no repositório para garantir auditabilidade, reprodutibilidade e onboarding instantâneo. Veja detalhes em [`docs/adr/001-versionamento-base-conhecimento.md`](docs/adr/001-versionamento-base-conhecimento.md).

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
| **Ingester** | `.ingester/` | Crawl → normalize → curate CSA sources into OKF bundle |
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

### Extração de texto de PDFs

`web_csa_fetch(url_pdf, extract_text=True)` baixa o PDF oficial para
`.cache/csa-web/bin/` e retorna `path`, `size_bytes`, `content_type` e
`fetched_at`. Quando a leitura funciona, o campo `text` contém o texto
extraído. Quando falha, o campo `text_error` explica a causa; nesse caso o
agente deve informar a limitação e não afirmar conteúdo interno do PDF.

A extração tenta `pdftotext` primeiro e usa `pypdf` como fallback Python.
`pypdf` é instalado junto com as dependências do projeto (`uv sync` ou
`pip install .`). Para melhorar a fidelidade de layout localmente, instale
também o Poppler:

```bash
# Debian/Ubuntu
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

No Windows, instale uma distribuição do Poppler e adicione a pasta que contém
`pdftotext.exe` ao `PATH`. A imagem Docker do projeto já inclui
`poppler-utils`.

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
# frontend respects VITE_CONSUMER_URL at build time
```

> **Why two vars?** `AGENT_CONFIG_DIR` is per-process (one agent = one dir + one port). `.env.example` therefore ships **both** `INGESTER_CONFIG_DIR` + `CONSUMER_CONFIG_DIR` (and `INGESTER_PORT`/`CONSUMER_PORT`) plus a fallback `AGENT_CONFIG_DIR`/`PORT` for single-agent mode. `Makefile` and `docker-compose.yml` read the `INGESTER_*`/`CONSUMER_*` set; the server itself still honors `AGENT_CONFIG_DIR` per instance.

### Painel do ingester (FastHTML /admin)

O ingester tem painel próprio servido pelo próprio backend — sem passar pelo frontend React (decisão registrada na discussão `ingester-fasthtml-admin`).

- **Rota**: `GET /admin` no servidor do ingester (`AGENT_CONFIG_DIR=.ingester`, porta `:8001` em dev). O mount só existe no config do ingester; o consumer permanece API pura (404 em `/admin`).
- **Login**: `POST /admin/login` valida contra o `auth_store` em memória (seed: `admin / sudo123`) e abre sessão por cookie HttpOnly (`csa_admin_token`, SameSite=Lax, path=/admin). `POST /admin/logout` encerra.
- **Chat**: painel autenticado conversa com o agente ingester via SSE contra `POST /v1/chat/completions` (mesmo origin, sem token manual). Histórico fica no cliente; servidor stateless por request.
- **Escopo mínimo**: login + chat apenas. O CRUD de usuários segue como JSON API (`/admin/users`, Bearer).
- **Deploy https (ex.: Vercel)**: definir `ADMIN_COOKIE_SECURE=1` para o cookie de sessão ser marcado Secure.
- **Caveat serverless**: o `auth_store` é em memória — em cold starts/instâncias múltiplas do Vercel, sessões e usuários resetam (comportamento pré-existente de `/auth/login` e `/admin/users`).

### React Chat (frontend/)

Vite + React chat widget **exclusivo do consumer** — botão flutuante que conversa com o agente consumer via endpoint OpenAI-compatible.

```bash
cp frontend/.env.example frontend/.env   # VITE_CONSUMER_URL=http://localhost:8002
make frontend-install
make frontend-dev      # http://localhost:5173
make frontend-build    # production build -> frontend/dist (served by nginx in docker)
```

- **Consumer**: open chat, no login.
- **Ingester**: painel próprio em FastHTML servido pelo backend (`/admin`), com tela de login e chat SSE — o frontend React não participa mais.
- Env: `VITE_CONSUMER_URL` (default 8002). Com Docker Compose o frontend fica em `http://localhost:5173` e conversa com o consumer em `:8002`.

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

See `knowledge/index.md` for the OKF bundle structure.

## 🚧 Status

**Em desenvolvimento.**

As funcionalidades, arquitetura e base de conhecimento estão sendo desenvolvidas e avaliadas durante a execução do projeto de extensão.

## ⚠️ Aviso

O Chat CSA é um projeto acadêmico e experimental.

As respostas produzidas pelo assistente têm caráter informativo e devem ser verificadas nos canais oficiais da Universidade Estadual de Feira de Santana.

Em caso de divergência, **os editais, resoluções, comunicados e demais publicações oficiais da CSA/UEFS têm precedência sobre qualquer resposta apresentada pelo sistema.**
