.PHONY: help install dev run run-ingester run-consumer prompt-ingester prompt-consumer lint format test docker-build docker-run clean frontend-install frontend-dev frontend-build deploy-api deploy-frontend deploy-env

# Usa uv se disponível; senão, cai para pip
UV ?= uv
PYTHON ?= python3
HOST ?= 0.0.0.0

# Config dirs e portas dos dois agentes (sobrescreva via env ou `make VAR=...`)
# .env é carregado pelo python-dotenv em runtime; make lê env vars do shell.
# Para `make run-both` você precisa dos DOIS conjuntos — veja .env.example.
INGESTER_CONFIG_DIR ?= .ingester
INGESTER_PORT ?= 8001
CONSUMER_CONFIG_DIR ?= .consumer
CONSUMER_PORT ?= 8002
# Aliases retrocompatíveis (para PORT_INGESTER=... continuar funcionando)
PORT_INGESTER ?= $(INGESTER_PORT)
PORT_CONSUMER ?= $(CONSUMER_PORT)

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências (uv sync)
	$(UV) sync

dev: ## Instala com dependências de dev
	$(UV) sync --group dev

run: run-ingester ## Atalho para run-ingester

run-ingester: ## Roda o agente ingester (compat OpenAI+Ollama) na :$(INGESTER_PORT)
	$(UV) run chat-csa serve --config-dir $(INGESTER_CONFIG_DIR) --host $(HOST) --port $(INGESTER_PORT)

run-consumer: ## Roda o agente consumer na :$(CONSUMER_PORT)
	$(UV) run chat-csa serve --config-dir $(CONSUMER_CONFIG_DIR) --host $(HOST) --port $(CONSUMER_PORT)

run-both: ## Roda os dois agentes em paralelo (exige concurrently ou make -j)
	@echo "Starting ingester $(INGESTER_CONFIG_DIR):$(INGESTER_PORT) and consumer $(CONSUMER_CONFIG_DIR):$(CONSUMER_PORT) ..."
	@$(MAKE) -j2 run-ingester run-consumer

prompt-ingester: ## Imprime o system prompt composto do ingester
	$(UV) run chat-csa print-prompt --config-dir $(INGESTER_CONFIG_DIR)

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

docker-run: ## Roda o Docker (padrão: ingester)
	docker run --rm -p 8000:8000 --env-file .env -e AGENT_CONFIG_DIR=$(INGESTER_CONFIG_DIR) chat-csa:latest

docker-run-consumer: ## Roda o Docker como consumer
	docker run --rm -p 8002:8000 -e AGENT_CONFIG_DIR=$(CONSUMER_CONFIG_DIR) -e LLM_PROVIDER=ollama -e OLLAMA_BASE_URL=http://host.docker.internal:11434 chat-csa:latest

docker-run-both: ## Roda os dois agentes via compose
	docker compose up --build

frontend-install: ## Instala dependências do frontend
	cd frontend && npm install

frontend-dev: ## Roda o dev server React (conecta automático ao ingester/consumer)
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
