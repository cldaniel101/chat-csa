# Desenvolvimento

Este documento cobre o ambiente de desenvolvimento local do Chat CSA: pré-requisitos, instalação, execução dos dois agentes e do frontend, e os atalhos do Makefile usados no dia a dia. Ele assume que os arquivos de configuração existem como documentado em [configuracao.md](./configuracao.md); para a visão geral da arquitetura, veja [arquitetura.md](./arquitetura.md).

## Pré-requisitos

| Ferramenta | Versão / observação | Evidência |
|---|---|---|
| Python | 3.11 (fixado) — `pyproject.toml` aceita `>=3.10` | `.python-version`, `pyproject.toml` (`requires-python`) |
| uv | gerenciador de pacotes do projeto | `pyproject.toml` (`[dependency-groups]`, `[tool.uv]`), `uv.lock` |
| Node + npm | 20 (imagem `node:20-alpine` do frontend) | `frontend/Dockerfile` |
| Ollama ou API OpenAI-compatible | provedor de LLM; o default é Ollama | `.env.example` |

O projeto usa **uv** em vez de pip/venv porque o `pyproject.toml` já declara o grupo de dependências de dev e o `uv.lock` versiona a árvore inteira — a mesma resolução vale para qualquer máquina e para o CI do scraper (`.github/workflows/scrape-csa.yml` roda `uv sync --frozen`).

## Passo a passo (backend)

```bash
cp .env.example .env      # um único agente + KB_* da base remota
uv sync --group dev       # equivalente a `make dev`

make run-consumer         # consumer em :8002
```

O alvo lê `CONSUMER_CONFIG_DIR`/`CONSUMER_PORT` do ambiente (o `.env` é carregado pelo python-dotenv em runtime). Para conferir o system prompt composto sem subir servidor:

```bash
make prompt-consumer
# equivalente direto:
uv run chat-csa print-prompt --config-dir .consumer
```

Verificação rápida com a API no ar:

```bash
curl http://localhost:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"quais documentos para matrícula?"}]}'
```

## Variáveis de ambiente do desenvolvimento

O `.env.example` é a referência completa. As essenciais para rodar localmente:

| Variável | Papel | Default no `.env.example` |
|---|---|---|
| `LLM_PROVIDER` | provedor compartilhado (`ollama` ou `openai`) | `ollama` |
| `LLM_MODEL` / `OLLAMA_MODEL` | modelo usado quando o agente não define o próprio | `gemma4:31b-cloud` |
| `OLLAMA_BASE_URL` | endpoint do Ollama (local ou nuvem) | `http://localhost:11434` |
| `OLLAMA_API_KEY` | token do Ollama Cloud (o Ollama local ignora) | vazio |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | alternativa OpenAI-compatible | comentados |
| `AGENT_CONFIG_DIR` | config dir do agente | `.consumer` |
| `CONSUMER_CONFIG_DIR` / `CONSUMER_PORT` | dir e porta do consumer | `.consumer` / `8002` |
| `CONSUMER_*` (ex.: `CONSUMER_LLM_PROVIDER`) | override do consumer | comentados |
| `KB_BACKEND` | `github` (deploy) ou `local` (dev/testes sem rede) | `github` |
| `KB_REPO` / `KB_BRANCH` | repositório e branch da base | `cldaniel101/chat-csa` / `data` |
| `KB_TOKEN` / `KB_WRITE_TOKEN` | leitura / escrita da base | vazios |
| `KB_LOCAL_PATH` | diretório da base no backend local | `knowledge` |

A base remota é a fonte primária; em dev, `KB_BACKEND=local` + `KB_LOCAL_PATH=knowledge` (pasta gitignored) permitem trabalhar sem rede. O `.env.example` é a referência completa, incluindo `KB_CACHE_TTL` e `CHAT_CSA_PORTAL_TOOLS`.

## Frontend

O frontend React atende o consumer (o agente único). Veja [design-system.md](./design-system.md) e [api.md](./api.md).

```bash
cp frontend/.env.example frontend/.env   # VITE_CONSUMER_URL=http://localhost:8002
make frontend-install                    # cd frontend && npm install
make frontend-dev                        # http://localhost:5173
make frontend-build                      # bundle de produção em frontend/dist
```

Scripts disponíveis em `frontend/package.json`: `dev` (vite), `build` (`tsc -b && vite build`), `lint` (oxlint), `preview`.

## Qualidade e limpeza

```bash
make lint     # uv run ruff check src
make format   # uv run ruff check --fix src
make test     # uv run pytest -v   (detalhes em testes.md)
make clean    # remove .venv, caches e frontend/dist
```

## Alternativa sem uv: Docker

O `Dockerfile` da raiz instala o pacote com `pip install .` e já inclui `poppler-utils` (necessário para extrair texto de PDFs). O caminho sem uv é `make docker-build` + `make docker-run` (consumer) ou `make docker-run-both` (compose). Detalhes de deploy em [deploy.md](./deploy.md).

## Fontes

- `Makefile`
- `pyproject.toml`
- `.python-version`
- `.env.example`
- `frontend/package.json`
- `frontend/.env.example`
- `frontend/Dockerfile`
- `README.md` (quickstart, seção "Makefile DX")
- `src/chat_csa/cli.py`
