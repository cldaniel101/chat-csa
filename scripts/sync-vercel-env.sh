#!/usr/bin/env bash
# Sincroniza variáveis do .env para o projeto na Vercel de forma
# determinística e idempotente.
#
# Uso:
#   scripts/sync-vercel-env.sh [production|preview|development]
#
# - Fonte da verdade: .env local (gitignored).
# - Allowlist explícita: só o que o backend precisa em produção é enviado.
# - Overrides por ambiente: OLLAMA_BASE_URL aponta para o Ollama Cloud
#   em produção (o localhost do .env vale apenas para o dev local).
# - Valores nunca são impressos; a saída mostra só o nome das variáveis.

set -euo pipefail

ENV_FILE=".env"
TARGET_ENV="${1:-production}"

if [ ! -f "$ENV_FILE" ]; then
  echo "erro: $ENV_FILE não encontrado na raiz do projeto" >&2
  exit 1
fi

# Allowlist: variáveis que o backend consome em produção
KEYS=(LLM_PROVIDER LLM_MODEL OLLAMA_MODEL OLLAMA_BASE_URL OLLAMA_API_KEY)

# Overrides de produção (o .env local mantém localhost para dev)
declare -A OVERRIDES=()
if [ "$TARGET_ENV" = "production" ]; then
  OVERRIDES[OLLAMA_BASE_URL]="https://ollama.com"
fi

for key in "${KEYS[@]}"; do
  val="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\"')"
  if [ -z "$val" ]; then
    echo "aviso: ${key} ausente em ${ENV_FILE} — pulando"
    continue
  fi
  if [ -n "${OVERRIDES[$key]:-}" ]; then
    val="${OVERRIDES[$key]}"
  fi
  # remove versão anterior (se existir) e recria — garante idempotência
  vercel env rm "$key" "$TARGET_ENV" -y >/dev/null 2>&1 || true
  printf '%s' "$val" | vercel env add "$key" "$TARGET_ENV" >/dev/null
  echo "ok: ${key} -> ${TARGET_ENV}"
done

echo "sincronização concluída (${TARGET_ENV})."
