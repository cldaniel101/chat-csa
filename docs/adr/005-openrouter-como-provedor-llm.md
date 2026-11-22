# ADR-005: OpenRouter como provedor de LLM (substitui o Ollama)

**Data:** 2026-11-22
**Status:** Aceita
**Decisores:** Equipe Chat CSA
**Substitui:** o provedor Ollama descrito em [ADR-003](./003-simplificacao-arquitetura-devops.md). A ADR-003 continua válida para o restante da arquitetura DevOps.

---

## 1. Contexto

O Chat CSA usava o Ollama como provedor padrão, inicialmente via `OLLAMA_BASE_URL=http://localhost:11434` e, no deploy, via Ollama Cloud (`gemma4:31b-cloud`) com `OLLAMA_API_KEY` no header `Authorization`.

O Ollama deixou de oferecer acesso gratuito aos modelos de nuvem. Manter o provedor significaria pagar por chamadas de nuvem ou exigir uma GPU local no ambiente de execução — inviável na Vercel, onde a função serverless não tem runtime de inferência.

O projeto precisa de um provedor com:

- endpoint compatível com OpenAI (o SDK/`ChatOpenAI` já é usado para o provedor `openai`);
- suporte a **tool calling** (o agente depende de `kb_list`/`kb_read` no laço ReAct);
- tier gratuito para desenvolvimento e para o protótipo de extensão;
- chave por variável de ambiente, sem credencial no repositório.

## 2. Decisão

Adotar o **OpenRouter** como provedor padrão (`LLM_PROVIDER=openrouter`), usando o endpoint compatível com OpenAI `https://openrouter.ai/api/v1` e modelos com sufixo `:free`.

Concretamente:

- `agent/factory.py` ganhou o ramo `openrouter`, que monta `ChatOpenAI` com:
  - `api_key` de `OPENROUTER_API_KEY` (obrigatória; erro explícito se ausente);
  - `base_url` de `OPENROUTER_BASE_URL` (padrão `https://openrouter.ai/api/v1`);
  - `max_tokens` de `LLM_MAX_TOKENS` (padrão `1024`) — modelos de *reasoning* gastam tokens antes de emitir texto e, sem teto, devolvem `content: null` com `finish_reason: "length"`;
  - `timeout` de `LLM_TIMEOUT_S` (padrão `60`) e `max_retries` de `LLM_MAX_RETRIES` (padrão `2`);
  - cabeçalhos opcionais `HTTP-Referer`/`X-Title` a partir de `OPENROUTER_SITE_URL`/`OPENROUTER_APP_NAME`.
- O provedor `ollama` foi **removido** e a dependência `langchain-ollama` saiu de `pyproject.toml`, `api/requirements.txt` e `uv.lock`.
- O padrão passou de `ollama` para `openrouter` em `get_llm`, no `Dockerfile`, no `docker-compose.yml` e no `.env.example`.
- A **superfície HTTP** no formato do Ollama (`POST /api/chat`, `GET /api/tags`) permanece: ela é compatibilidade de *entrada* para clientes existentes e não depende do runtime do Ollama. O mesmo vale para `examples/ollama_client.py`, que exercita o shim.
- A chave vive apenas em `.env` (ignorado pelo Git) e nas variáveis de ambiente do deploy. Nenhum valor é versionado, impresso em log ou exposto ao frontend.

## 3. Consequências

**Positivas**

- Zero dependência de runtime local de inferência; funciona na Vercel.
- Troca de modelo é uma variável de ambiente (`LLM_MODEL`), sem mudança de código.
- Um único cliente (`ChatOpenAI`) atende OpenRouter e OpenAI puro, reduzindo superfície.

**Negativas e riscos**

- **Limite diário de requisições do tier gratuito.** A conta usada no desenvolvimento reportou `free_model_daily_requests.limit = 50` (o valor cresce com créditos comprados). Como cada turno do agente faz várias chamadas (uma por passo do ReAct), o limite comporta poucas dezenas de perguntas por dia. Para o protótipo público, é preciso acompanhar `GET /api/v1/key` e considerar créditos ou um provedor pago.
- **`429` do pool compartilhado.** Modelos gratuitos populares podem devolver `429 upstream_provider_shared_pool` mesmo com cota disponível; modelos menos disputados e o roteador `openrouter/free` são mais estáveis.
- **Variação de qualidade entre modelos gratuitos.** A aderência ao contrato de citação (`Fontes:` com URL) depende do modelo escolhido; deve ser verificada ao trocar `LLM_MODEL`.
- **Dependência de terceiro.** O OpenRouter intermedeia o acesso; indisponibilidade do serviço afeta o chat (as rotas `/health` e `/v1/models` continuam respondendo, o que exige um smoke test de completion).
- **Custo futuro.** Modelos `:free` podem mudar de preço ou sair do catálogo; fixar ids sem revisão deixa o serviço quebrado sem deploy.

## 4. Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter Ollama Cloud pago | Contraria o objetivo do protótipo gratuito e mantém dependência de runtime que a Vercel não oferece |
| Ollama local em VM/GPU | Custo e operação incompatíveis com o time e com o deploy serverless |
| OpenAI puro | Sem tier gratuito; o código já suporta (`LLM_PROVIDER=openai`), fica como alternativa |
| Outro agregador (Groq, Together, etc.) | Também viáveis pelo mesmo endpoint OpenAI; o OpenRouter foi escolhido pelo catálogo amplo de modelos gratuitos e pela troca de modelo por env var |

## 5. Como reverter

`LLM_PROVIDER=openai` + `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`OPENAI_MODEL` restaura um provedor compatível com OpenAI sem tocar no código. Reintroduzir o Ollama exigiria restaurar o ramo `ollama` em `agent/factory.py` e a dependência `langchain-ollama`.
