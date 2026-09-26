# Padrões de projeto

Este documento reúne os padrões estruturais que se repetem no código do Chat CSA: como o agente é montado, como as ferramentas são registradas, por que a configuração vive em Markdown, como a FAQ é recuperada e por que a rede é tratada com polidez. Ele é útil para quem vai adicionar um provedor, uma ferramenta ou uma skill sem quebrar as convenções existentes.

## 1. Fábrica de agente com troca de provedor

`agent/factory.py` concentra a criação do LLM e do agente. O provedor é resolvido em cascata (`get_llm`): argumento → `LLM_PROVIDER` → `ollama`; o modelo segue `LLM_MODEL` → `MODEL` → default do provedor (`OLLAMA_MODEL` ou `OPENAI_MODEL`). Três provedores são suportados:

- `openai` — `ChatOpenAI` com `base_url` opcional, cobrindo Azure/OpenRouter/proxies;
- `ollama` — `ChatOllama`, com header Bearer via `client_kwargs` quando há `OLLAMA_API_KEY` e `reasoning` ligado por padrão;
- `fake` — um `FakeListChatModel` com `bind_tools` no-op, usado pelos testes para rodar sem LLM.

O motivo de existir uma fábrica (em vez de instanciar o LLM no servidor) é duplo: o mesmo servidor atende OpenAI e Ollama sem ramificação nas rotas, e os testes trocam o provedor por configuração, sem mock de rede. A montagem do agente tenta `langchain.agents.create_agent` e cai para `langgraph.prebuilt.create_react_agent` — um fallback de compatibilidade entre versões do LangChain.

## 2. Registro de ferramentas controlado pelo config dir

As ferramentas são funções decoradas com `@tool` (`agent/tools.py`), agrupadas em dois conjuntos explícitos: `ALL_TOOLS` (`read`, `write`, `edit`, `bash`) e `CSA_TOOLS` (`web_csa_fetch`, `web_csa_search`). O mapa `TOOL_MAP` permite consulta por nome. `tools_for_config` decide o conjunto pelo **nome do config dir**: `.ingester` recebe tudo; `.consumer` recebe apenas `read` + `CSA_TOOLS`; `CHAT_CSA_EXTRA_TOOLS` força `none`/`ingester`/`consumer`.

O padrão relevante é o **menor privilégio por padrão**: o consumer não recebe `bash`, `write` nem `edit`, porque o papel dele é responder, não alterar o acervo. As ferramentas de arquivo truncam a saída em 50KB/2000 linhas, espelhando a semântica de leitura usada no restante do projeto.

## 3. Configuração viva em Markdown

`agent/prompt.py` compõe o system prompt a cada request: identidade base + `AGENTS.md` do config dir + todos os `skills/*/SKILL.md` (ordenados) + blocos extras. Não há cache; criar uma pasta em `.ingester/skills/` é suficiente para adicionar comportamento. O motivo é operacional: curadoria e ajuste de prompt são atividades de conteúdo, não de código — editar um `.md` não exige rebuild nem restart. O layout espelha o "AGENTS home" (um diretório com `AGENTS.md` + `skills/`) e é por isso que `.ingester`/`.consumer` ficam na raiz, fora do pacote.

## 4. Cache de QA determinístico (referência, não resposta)

`qa_cache.py` lê a FAQ curada em Markdown (frontmatter + entradas `FAQ-XXX`) e a transforma em `QACacheEntry`/`QACacheHit` — dataclasses **frozen**, ou seja, imutáveis. O ranking usa `difflib.SequenceMatcher` com normalização, remoção de stopwords e limiar configurável (`CHAT_CSA_QA_CACHE_MIN_SCORE`, default `0.68`).

O padrão decisivo está no contrato: as entradas são injetadas no prompt como **referência curada**, nunca como resposta pronta — o servidor não faz short-circuit. Entradas marcadas como `dynamic` entram com aviso explícito para conferência nas fontes. O motivo é reduzir alucinação sem congelar a resposta: o LLM adapta o conteúdo ao contexto da conversa e cita a URL do frontmatter, e a FAQ pode evoluir sem que o código mude.

## 5. Modelos Pydantic como contrato de fronteira

`server/models.py` define `ChatMessage`, `ChatCompletionRequest`, `ModelCard` e `ModelsResponse` em Pydantic v2. Duas escolhas importam: `content: Any` (aceita string ou lista de partes enviada por SDKs) e `model_config = {"extra": "allow"}`, que deixa a requisição carregar campos desconhecidos em vez de recusá-la. O servidor valida o que precisa e ignora o resto — o objetivo é compatibilidade com clientes OpenAI/Ollama reais, não pureza de schema. As respostas de erro usam `HTTPException` (auth) ou o envelope `{"error": {...}}` (streaming e rotas de chat).

## 6. Cliente HTTP estruturalmente educado e com cache

`csa_portal.py` trata rede como um recurso de terceiros: allowlist obrigatória de host (`csa.uefs.br`), intervalo mínimo entre requests (`CSA_MIN_INTERVAL_S`, default 3s) com concorrência 1 via lock global, backoff exponencial em 429/5xx honrando `Retry-After` e cache em disco com TTL de 1h (`.cache/csa-web`, gitignored). A extração de PDF usa `pdftotext` e cai para `pypdf`, devolvendo `pdf_extraction_status` explícito (`completed`/`partial`/`failed`) em vez de texto vazio silencioso; mudança no schema dos endpoints JSON falha alto. O comentário estruturante do módulo diz que a polidez é **estrutural, nunca em prompt** — regra que o LLM não pode esquecer, o código garante.

## Fontes

- `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/tools.py`, `src/chat_csa/agent/prompt.py`
- `src/chat_csa/qa_cache.py`
- `src/chat_csa/server/models.py`, `src/chat_csa/server/app.py`
- `src/chat_csa/csa_portal.py`
- `tests/test_tools.py`, `tests/test_qa_cache.py`, `tests/test_csa_portal.py`
