# Dockerfile — sem necessidade de uv para o usuário final
# Quem não tem uv pode `docker build -t chat-csa . && docker run -p 8000:8000 chat-csa`

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dependências de sistema (curl para healthcheck, poppler-utils para ler PDFs)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    curl ca-certificates poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala as deps Python primeiro (cache de camada)
COPY pyproject.toml README.md ./
# Fornece um ambiente de build mínimo de hatchling para o pip instalar sem uv
COPY src ./src
RUN pip install --upgrade pip hatchling && pip install .

# Copia o restante (AGENTS, skills etc.)
COPY .ingester ./.ingester
COPY .consumer ./.consumer
# Mantém outros arquivos do projeto usados como referência
COPY docs ./docs

# Env padrão — sobrescreva em runtime
ENV AGENT_CONFIG_DIR=.ingester \
    LLM_PROVIDER=ollama \
    OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    LLM_MODEL=gemma4:31b-cloud \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/health || exit 1

# Roda o servidor compatível com a OpenAI
CMD ["sh", "-c", "python -m chat_csa.cli serve --config-dir ${AGENT_CONFIG_DIR} --host ${HOST} --port ${PORT}"]
