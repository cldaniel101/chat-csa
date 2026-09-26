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
cp .env.example .env      # o .env.example já traz os DOIS agentes e os defaults compartilhados
uv sync --group dev       # equivalente a `make dev`

make run-ingester         # ingester  em :8001
make run-consumer         # consumer  em :8002
make run-both             # os dois em paralelo (make -j2)
```

Os alvos leem `INGESTER_CONFIG_DIR`/`INGESTER_PORT` e `CONSUMER_CONFIG_DIR`/`CONSUMER_PORT` do ambiente (o `.env` é carregado pelo python-dotenv em runtime). Para conferir o system prompt composto sem subir servidor:

```bash
make prompt-ingester
make prompt-consumer
# equivalente direto:
uv run chat-csa print-prompt --config-dir .ingester
```

Verificação rápida com a API no ar:

```bash
curl http://localhost:8001/v1/chat/completions \
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
| `AGENT_CONFIG_DIR` | config dir do modo de agente único | `.ingester` |
| `INGESTER_CONFIG_DIR` / `INGESTER_PORT` | dir e porta do ingester | `.ingester` / `8001` |
| `CONSUMER_CONFIG_DIR` / `CONSUMER_PORT` | dir e porta do consumer | `.consumer` / `8002` |
| `INGESTER_*` / `CONSUMER_*` (ex.: `INGESTER_LLM_PROVIDER`) | override por agente | comentados |

Cada agente é um processo separado com seu próprio *AGENTS home* (`.ingester/` ou `.consumer/`); é por isso que a configuração existe em dois conjuntos e que `make run-both` precisa dos dois.

## Frontend

O frontend React atende somente o consumer; o painel do ingester é servido pelo próprio backend em `/admin` (veja [design-system.md](./design-system.md) e [api.md](./api.md)).

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

O `Dockerfile` da raiz instala o pacote com `pip install .` e já inclui `poppler-utils` (necessário para extrair texto de PDFs). O caminho sem uv é `make docker-build` + `make docker-run` (ingester), `make docker-run-consumer` ou `make docker-run-both` (compose). Detalhes de deploy em [deploy.md](./deploy.md).

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
