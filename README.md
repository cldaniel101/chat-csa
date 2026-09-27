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
2. O agente **consumer** busca informações relevantes na base de conhecimento remota (bundle OKF, branch `data` do repositório) e, se as ferramentas do portal estiverem ligadas, consulta o portal da CSA diretamente.
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

## 🧠 Arquitetura — Base remota + recuperação determinística

O projeto **não utiliza RAG** (embeddings vetoriais + geração aumentada por recuperação). Em vez disso, adota uma abordagem **determinística e auditável**, baseada em um bundle de conhecimento curado no formato **OKF — Open Knowledge Format** e em recuperação determinística por consulta direta aos conceitos curados (e ao portal da CSA, quando ligado):

```text
Fontes oficiais da CSA/UEFS (portal csa.uefs.br, PDFs)
        ↓  time (curadoria humana) → POST /kb/upload (auth admin)
Base de conhecimento remota (branch órfão `data`, bundle OKF na raiz)
        ↓  (recuperação determinística — kb_list/kb_read + cache TTL)
Agente consumer — resposta extrativa com citações
        ↓
Usuário (resposta verificável, com URL e timestamp)
```

Motivações principais dessa escolha:

* **Zero alucinação no caminho crítico**: as respostas são extrativas, extraídas verbatim de conceitos curados;
* **Auditabilidade**: cada frase é rastreável até uma fonte oficial;
* **Terminologia literal**: consultas sobre SISU são lexicais ("comprovante de cota racial", "lista de espera") — correspondência lexical supera busca semântica;
* **Custo e simplicidade**: sem banco vetorial nem API de embeddings — roda offline e barato;
* **Conteúdo separado do código**: a base vive num branch órfão (`data`) e é atualizada pelo time sem deploy.

O consumer responde consultando diretamente os conceitos da base (`kb_list`/`kb_read`), com as ferramentas do portal disponíveis como complemento opcional.

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

A base de conhecimento do Chat CSA é um conjunto de arquivos Markdown curados no formato **OKF (Open Knowledge Format)**, organizados na **raiz do branch órfão `data`** do próprio repositório. Ela é a **fonte única da verdade** usada pelo agente consumer para responder perguntas — e é lida em runtime pela API do GitHub, com cache TTL em memória.

O código (branches de desenvolvimento) não carrega mais o conteúdo: a base é atualizada pelo time pelo endpoint `POST /kb/upload` (login admin), que grava tudo em **um único commit atômico** no branch `data`. O branch nasce com um `README.md` explicando o fluxo.

```bash
# Ver a base publicada (branch data, órfão — não tem código)
git fetch origin data && git ls-tree -r origin/data
```

### Estrutura (no branch `data`)

```text
├── README.md                   # explica o branch e como enviar arquivos
├── index.md                    # Índice raiz — categorias e convenções
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
- Toda alteração é rastreada via Git (`git blame`, `git log`) no branch `data` — cada upload é um commit.

> **Decisão arquitetural:** o conteúdo foi separado do código num branch órfão, lido em runtime e atualizado por upload. Veja detalhes em [`docs/adr/002-base-conhecimento-branch-data.md`](docs/adr/002-base-conhecimento-branch-data.md) (que substitui a [ADR-001](docs/adr/001-versionamento-base-conhecimento.md)).

### Base local (dev/testes)

Para desenvolver sem rede, use o backend local do cliente: `KB_BACKEND=local` e `KB_LOCAL_PATH=knowledge` (a pasta `knowledge/` é gitignored e nunca versionada).

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

Registros autorais vivem em [`docs/DESIGN.md`](docs/DESIGN.md) (design system) e [`docs/adr/`](docs/adr/) (decisões). Os guias por tema ficam em `docs/`:

| Documento | Cobre |
|---|---|
| [`docs/desenvolvimento.md`](docs/desenvolvimento.md) | Setup local, Makefile, frontend e Docker |
| [`docs/estrutura.md`](docs/estrutura.md) | Mapa de diretórios do repositório |
| [`docs/api.md`](docs/api.md) | Rotas OpenAI/Ollama, auth e superfície admin `/kb/*` |
| [`docs/configuracao.md`](docs/configuracao.md) | Variáveis de ambiente e configuração |
| [`docs/arquitetura.md`](docs/arquitetura.md) | Base remota (branch `data`), o agente consumer e o fluxo de uma resposta |
| [`docs/testes.md`](docs/testes.md) | Suíte offline e contrato de citação |
| [`docs/deploy.md`](docs/deploy.md) | Vercel, GitHub Actions e scrape manual |
| [`docs/padroes.md`](docs/padroes.md) | Padrões de código (fábrica, tools, cache de QA) |
| [`docs/design-system.md`](docs/design-system.md) | Tokens e uso do design system CSA |
| [`docs/seguranca.md`](docs/seguranca.md) | Auth, CORS, sandbox e riscos conhecidos |

## 🤖 Agente — LangChain + Skills (`.consumer`)

O repositório tem **um único agente** (consumer), com um sistema de skills que espelha `.agents/`:

| Agent | Config dir | Purpose |
|-------|------------|---------|
| **Consumer** | `.consumer/` | Answer questions from the remote knowledge base (extractive, cited) |

`.consumer/` é o *AGENTS home*:
```
.consumer/
  AGENTS.md           # project instructions for the agent
  skills/
    csa-query/
      SKILL.md        # skill description (any .md folder counts)
```
Qualquer `.md` de skill é concatenado no system prompt (hot-reloaded every request). Add a skill by creating a folder:
```bash
mkdir -p .consumer/skills/my-skill
cat > .consumer/skills/my-skill/SKILL.md <<'EOF'
---
name: my-skill
description: does X
allowed-tools: kb_list kb_read
---
# My skill — instructions for the agent
EOF
```

**Tools do agente:** `kb_list(prefix)`, `kb_read(path)` — leitura da base remota em processo (sem HTTP, sem credencial de admin). Com `CHAT_CSA_PORTAL_TOOLS=1`, entram também `web_csa_fetch` e `web_csa_search` (desligadas por padrão).

**API:** OpenAI-compatible (`POST /v1/chat/completions`, `GET /v1/models`) **+** Ollama-native shim (`POST /api/chat`, `GET /api/tags`). Works with the OpenAI SDK, `curl`, and Ollama clients pointing at `http://localhost:8001/v1`.

### Quickstart (uv)

```bash
cp .env.example .env   # consumer: .consumer :8002 + KB_* da base remota
uv sync --group dev
uv run chat-csa print-prompt --config-dir .consumer   # debug prompt
make run-consumer   # :8002  (uses CONSUMER_CONFIG_DIR/CONSUMER_PORT)
# In another shell — OpenAI SDK example
curl http://localhost:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"quais documentos para matrícula?"}]}'
# Ollama shim
curl http://localhost:8002/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"oi"}]}'
```

Single agent (override per-run):
```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma4:31b-cloud uv run chat-csa serve --config-dir .consumer --port 8002
LLM_PROVIDER=openai OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini uv run chat-csa serve --config-dir .consumer --port 8002
```

Base remota em dev: por padrão o cliente usa o backend `github` (`KB_REPO`/`KB_BRANCH=data`). Para testar sem rede, use `KB_BACKEND=local` e `KB_LOCAL_PATH=knowledge` (pasta local gitignored).

Ollama local model (default):
```bash
ollama pull gemma4:31b-cloud
ollama serve  # default http://localhost:11434
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
docker run --rm -p 8002:8000 --env-file .env -e AGENT_CONFIG_DIR=.consumer chat-csa
make docker-build
docker compose up   # consumer :${CONSUMER_PORT:-8002} + frontend :${FRONTEND_PORT:-5173}
```

### React Chat (frontend/)

Vite + React chat widget **exclusivo do consumer** — botão flutuante que conversa com o agente consumer via endpoint OpenAI-compatible.

```bash
cp frontend/.env.example frontend/.env   # VITE_CONSUMER_URL=http://localhost:8002
make frontend-install
make frontend-dev      # http://localhost:5173
make frontend-build    # production build -> frontend/dist (served by nginx in docker)
```

- **Consumer**: open chat, no login.
- Env: `VITE_CONSUMER_URL` (default 8002). Com Docker Compose o frontend fica em `http://localhost:5173` e conversa com o consumer em `:8002`.

### Snippet de integração

Para incorporar o Chat CSA em páginas externas, use o script público do frontend:

```html
<script
  src="https://chat-csa-web.vercel.app/embed.js"
  data-chat-url="https://chat-csa-web.vercel.app"
  data-consumer-url="https://chat-csa-api.vercel.app"
  defer
></script>
```

Veja opções de configuração e exemplo local em [`docs/integracao-widget.md`](docs/integracao-widget.md).

### Makefile DX

| Target | What it does |
|--------|---------------|
| `make install` | `uv sync` |
| `make dev` | installs dev group |
| `make run-consumer` | consumer on `$CONSUMER_PORT` (`CONSUMER_CONFIG_DIR`) |
| `make prompt-consumer` | print composed system prompt (AGENTS.md + skills) |
| `make frontend-install` / `frontend-dev` / `frontend-build` | React app |
| `make lint` / `format` / `test` | ruff + pytest |
| `make docker-build` / `docker-run*` / `docker-run-both` | container flow |

See the branch `data` for the OKF bundle structure (read at runtime by the consumer).

## 🚀 Deploy (Vercel + GitHub Actions)

O deploy é automatizado via **GitHub Actions + Vercel CLI** (sem GitHub App), com dois projetos separados na Vercel:

| Projeto | Diretório | URL |
|---|---|---|
| **chat-csa-api** (backend FastAPI + superfície admin `/kb/*`) | raiz do repo (`vercel.json`, `api/index.py`) | `https://chat-csa-api.vercel.app` |
| **chat-csa-web** (frontend React/Vite) | `frontend/` (`frontend/vercel.json`) | *definido no painel da Vercel* |

### Fluxo do CI (`.github/workflows/deploy.yml`)

- `push` em **main** → deploy de produção nos dois projetos;
- `push` em **development** ou **pull request** → deploy de preview (URLs únicas por deploy).
- O job `checks` (lint + build) roda antes e bloqueia o deploy.
- Cada projeto usa um **token project-scoped** próprio, armazenado como secret do GitHub:
  `VERCEL_TOKEN_API`, `VERCEL_TOKEN_FRONTEND` (mais `VERCEL_ORG_ID_*` e `VERCEL_PROJECT_ID_*`).

### Variáveis de ambiente (`.github/workflows/env-sync.yml`)

O backend consome `LLM_PROVIDER`, `LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` e as variáveis `KB_*` da base remota (`KB_BACKEND`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL`).
Elas vivem como secrets do GitHub; para sincronizá-las nos ambientes da Vercel (production/preview/development),
rode manualmente **Actions → “Sync Vercel env”** — o workflow reutiliza `scripts/sync-vercel-env.sh`
(allowlist + override de `OLLAMA_BASE_URL=https://ollama.com` em produção).

### Deploy manual (alternativa)

```bash
make deploy-env        # sincroniza envs do backend (produção)
make deploy-api        # deploy do backend
make deploy-frontend   # deploy do frontend
```

> Pré-requisito local: `npx vercel link` uma vez em cada diretório (raiz e `frontend/`).

## 🚧 Status

**Em desenvolvimento.**

As funcionalidades, arquitetura e base de conhecimento estão sendo desenvolvidas e avaliadas durante a execução do projeto de extensão.

## ⚠️ Aviso

O Chat CSA é um projeto acadêmico e experimental.

As respostas produzidas pelo assistente têm caráter informativo e devem ser verificadas nos canais oficiais da Universidade Estadual de Feira de Santana.

Em caso de divergência, **os editais, resoluções, comunicados e demais publicações oficiais da CSA/UEFS têm precedência sobre qualquer resposta apresentada pelo sistema.**
