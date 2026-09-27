#!/usr/bin/env bash
# Sincroniza variáveis do .env para o projeto na Vercel de forma
# determinística e idempotente.
#
# Uso:
#   scripts/sync-vercel-env.sh [production|preview|development]
#
# - Fonte da verdade: .env local (gitignored) ou, no CI, o .env montado a
#   partir dos secrets do GitHub.
# - Allowlist explícita: só o que o backend precisa é enviado.
# - Overrides por ambiente: OLLAMA_BASE_URL aponta para o Ollama Cloud em
#   produção; KB_BACKEND vira github fora de development.
# - Valores nunca são impressos; a saída mostra só o nome das variáveis.
# - Com VERCEL_TOKEN + VERCEL_PROJECT_ID definidos (CI), usa a API REST —
#   tokens project-scoped não conseguem rodar `vercel env` (erro de scope).
#   Localmente, usa o CLI autenticado.

set -euo pipefail

ENV_FILE=".env"
TARGET_ENV="${1:-production}"

if [ ! -f "$ENV_FILE" ]; then
  echo "erro: $ENV_FILE não encontrado na raiz do projeto" >&2
  exit 1
fi

# Allowlist: variáveis que o backend consome no deploy
KEYS=(LLM_PROVIDER LLM_MODEL OLLAMA_MODEL OLLAMA_BASE_URL OLLAMA_API_KEY \
      KB_BACKEND KB_REPO KB_BRANCH KB_ROOT KB_TOKEN KB_WRITE_TOKEN KB_CACHE_TTL)

read_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' || true
}

push_api() {
  local key="$1" val="$2"
  local api="https://api.vercel.com/v10/projects/${VERCEL_PROJECT_ID}/env"
  local auth=(-H "Authorization: Bearer ${VERCEL_TOKEN}" -H "Content-Type: application/json")
  # remove entradas anteriores no alvo (idempotência)
  while IFS= read -r env_id; do
    if [ -n "$env_id" ]; then
      curl -fsS -X DELETE "${auth[@]}" "$api/$env_id" >/dev/null
    fi
  done < <(
    curl -fsS "${auth[@]}" "$api" \
      | jq -r --arg k "$key" --arg t "$TARGET_ENV" \
          '.envs[] | select(.key==$k and (.target|index($t))) | .id'
  )
  jq -n --arg k "$key" --arg v "$val" --arg t "$TARGET_ENV" \
      '{key:$k, value:$v, type:"encrypted", target:[$t]}' \
    | curl -fsS -X POST "${auth[@]}" --data @- "$api" >/dev/null
}

push_cli() {
  local key="$1" val="$2"
  vercel env rm "$key" "$TARGET_ENV" -y >/dev/null 2>&1 || true
  printf '%s' "$val" | vercel env add "$key" "$TARGET_ENV" >/dev/null
}

for key in "${KEYS[@]}"; do
  val="$(read_value "$key")"
  if [ -z "$val" ]; then
    echo "aviso: ${key} ausente em ${ENV_FILE} — pulando"
    continue
  fi
  # overrides por ambiente
  if [ "$key" = "OLLAMA_BASE_URL" ] && [ "$TARGET_ENV" = "production" ]; then
    val="https://ollama.com"
  fi
  if [ "$key" = "KB_BACKEND" ] && [ "$TARGET_ENV" != "development" ]; then
    val="github"
  fi

  if [ -n "${VERCEL_TOKEN:-}" ] && [ -n "${VERCEL_PROJECT_ID:-}" ]; then
    push_api "$key" "$val"
  else
    push_cli "$key" "$val"
  fi
  echo "ok: ${key} -> ${TARGET_ENV}"
done

echo "sincronização concluída (${TARGET_ENV})."
