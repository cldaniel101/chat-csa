.PHONY: help install dev run run-consumer prompt-consumer lint format test docker-build docker-run docker-run-consumer docker-run-both clean frontend-install frontend-dev frontend-build deploy-api deploy-frontend deploy-env

# Usa uv se disponível; senão, cai para pip
UV ?= uv
PYTHON ?= python3
HOST ?= 0.0.0.0

# Config dir e porta do consumer (sobrescreva via env ou `make VAR=...`)
# .env é carregado pelo python-dotenv em runtime; make lê env vars do shell.
CONSUMER_CONFIG_DIR ?= .consumer
CONSUMER_PORT ?= 8002
PORT_CONSUMER ?= $(CONSUMER_PORT)

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências (uv sync)
	$(UV) sync

dev: ## Instala com dependências de dev
	$(UV) sync --group dev

run: run-consumer ## Atalho para run-consumer

run-consumer: ## Roda o agente consumer na :$(CONSUMER_PORT)
	$(UV) run chat-csa serve --config-dir $(CONSUMER_CONFIG_DIR) --host $(HOST) --port $(CONSUMER_PORT)

prompt-consumer: ## Imprime o system prompt composto do consumer
	$(UV) run chat-csa print-prompt --config-dir $(CONSUMER_CONFIG_DIR)

lint: ## Lint (ruff)
	$(UV) run ruff check src

format: ## Formata (ruff)
	$(UV) run ruff check --fix src

test: ## Roda os testes
	$(UV) run pytest -v

docker-build: ## Constrói a imagem Docker (sem precisar de uv dentro)
	docker build -t chat-csa:latest .

docker-run: ## Roda o Docker como consumer
	docker run --rm -p 8002:8000 --env-file .env -e AGENT_CONFIG_DIR=$(CONSUMER_CONFIG_DIR) chat-csa:latest

docker-run-consumer: ## Roda o Docker como consumer (alias explícito)
	docker run --rm -p 8002:8000 -e AGENT_CONFIG_DIR=$(CONSUMER_CONFIG_DIR) -e LLM_PROVIDER=ollama -e OLLAMA_BASE_URL=http://host.docker.internal:11434 chat-csa:latest

docker-run-both: ## Sobe o compose (consumer + frontend)
	docker compose up --build

frontend-install: ## Instala dependências do frontend
	cd frontend && npm install

frontend-dev: ## Roda o dev server React (conecta automático ao consumer)
	cd frontend && npm run dev

frontend-build: ## Gera o bundle de produção do React
	cd frontend && npm run build

# Deploy manual na Vercel (alternativa ao CI — exige `vercel link` local uma vez por projeto)
deploy-api: ## Deploy do backend na Vercel — produção
	npx vercel deploy --prod --yes

deploy-frontend: ## Deploy do frontend na Vercel — produção
	cd frontend && npx vercel deploy --prod --yes

deploy-env: ## Sincroniza variáveis de ambiente do backend na Vercel (produção)
	./scripts/sync-vercel-env.sh production

clean: ## Remove caches
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache dist build frontend/dist
	find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
