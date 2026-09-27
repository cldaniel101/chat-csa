# Testes do Chat CSA

Guia completo de execução e descrição da suíte de testes do projeto.

## Pré-requisitos

O projeto usa [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes.

```bash
# Instalar uv (caso ainda não tenha)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Adicionar ao PATH (ou abrir novo terminal após a instalação)
export PATH="$HOME/.local/bin:$PATH"

# Instalar dependências de desenvolvimento
cd /caminho/para/chat_CSA_Extensao
uv sync --group dev
```

> **Dica permanente**: adicione `export PATH="$HOME/.local/bin:$PATH"` ao final
> do seu `~/.bashrc` para o `uv` ficar disponível em todo novo terminal.

---

## Como rodar os testes

```bash
# Todos os testes (recomendado)
uv run pytest tests/ -v

# Apenas um arquivo
uv run pytest tests/test_csa_portal.py -v
uv run pytest tests/test_citation_quality.py -v
uv run pytest tests/test_server.py -v
uv run pytest tests/test_tools.py -v

# Apenas um teste específico pelo nome
uv run pytest tests/ -k "test_cenario5"

# Com relatório de cobertura (requer pytest-cov instalado)
uv run pytest tests/ -v --cov=src/chat_csa --cov-report=term-missing
```

## Lint e formatação

```bash
# Verificar lint
uv run ruff check src

# Corrigir automaticamente o que for possível
uv run ruff check --fix src
```

---

## Estrutura da suíte

```
tests/
├── conftest.py              # fixtures: base local + reset do cliente kb
├── test_tools.py            # Ferramentas do consumer: kb_list/kb_read e renderização por tipo
├── test_server.py           # API FastAPI (health, modelos, completions, Ollama, FAQ no prompt)
├── test_kb.py               # Cliente da base: github falso (write atômico) e /kb/upload
├── test_admin.py            # Auth admin e CRUD /admin/users (painel removido)
├── test_qa_cache.py         # FAQ curada lida da base remota (backend local)
├── test_response_quality.py # Formatação da resposta e detecção de fonte aberta
├── test_csa_portal.py       # Portal CSA: fetch, busca, PDF, HTML, metadados
└── test_citation_quality.py # Qualidade de citação: 15 cenários obrigatórios
```

> Todos os testes são **offline** e **determinísticos** — não fazem requisições
> reais ao portal nem chamam nenhum LLM.

---

## Descrição detalhada por arquivo

### `test_tools.py` — Ferramentas do consumer (6 testes)

| Teste | O que verifica |
|-------|----------------|
| `test_kb_list_and_read_text` | `kb_list` acha o arquivo e `kb_read` devolve o texto (backend local) |
| `test_kb_read_csv_renders_markdown_table` | `.csv` vira tabela Markdown |
| `test_kb_read_pdf_extracts_text` | `.pdf` tem o texto extraído |
| `test_kb_read_binary_returns_notice` | binário vira aviso com tipo e tamanho |
| `test_kb_read_missing_returns_error` | caminho inexistente devolve erro claro |
| `test_prompt_build` | composição do system prompt a partir de `AGENTS.md` + skills |

---

### `test_server.py` — API do servidor (7 testes)

| Teste | O que verifica |
|-------|----------------|
| `test_health` | Endpoint `GET /health` retorna `status: ok` |
| `test_models` | Endpoint `GET /v1/models` lista os modelos disponíveis |
| `test_chat_completions_non_stream` | `POST /v1/chat/completions` sem streaming retorna resposta completa |
| `test_chat_completions_stream` | `POST /v1/chat/completions` com streaming retorna `text/event-stream` com `[DONE]` |
| `test_chat_completions_injects_cached_faq_as_context` | FAQ da base entra no prompt como referência (sem short-circuit) |
| `test_chat_completions_stream_with_cached_faq_uses_normal_flow` | FAQ em streaming segue o fluxo normal |
| `test_ollama_chat` | Endpoint Ollama `POST /api/chat` retorna `done: true` |

---

### `test_kb.py` — Cliente da base (6 testes)

| Teste | O que verifica |
|-------|----------------|
| `test_github_write_um_unico_commit_atomico` | `write` faz blobs + tree + commit + ref num único commit (API falsa) |
| `test_github_list_filtra_prefixo_e_raiz` | `list` filtra pelo prefixo e respeita `KB_ROOT` |
| `test_github_read_404_vira_erro_claro` | 404 vira `KBNotFoundError` com mensagem clara |
| `test_github_write_sem_token_falha_antes_de_qualquer_request` | sem `KB_WRITE_TOKEN`, falha sem tocar a API |
| `test_write_invalida_cache` | `write` invalida o cache de `list`/`read` (backend local) |
| `test_upload_endpoint_com_backend_github_falso` | `/kb/upload` commita o lote via backend github falso (sem commit real) |

---

### `test_admin.py` — Auth admin (3 testes)

| Teste | O que verifica |
|-------|----------------|
| `test_admin_users_requires_auth` | `/admin/users` responde 401 sem Bearer |
| `test_admin_users_crud` | Login + CRUD de usuários preservados |
| `test_admin_panel_removed` | O painel FastHTML foi removido (`/admin` é 404) |

---

### `test_qa_cache.py` — FAQ curada (7 testes)

Carrega a FAQ do prefixo `perguntas-frequentes/` da base (backend local nos
 testes) e cobre parsing, ranking por similaridade, entradas `dynamic` sem
short-circuit e a formatação sem vazar caminho de arquivo.

---

### `test_response_quality.py` — Formatação da resposta (7 testes)

Cobre `_format_agent_response`, `_is_conversational` e `_has_source_lookup`
(inclusive `kb_read` como fonte realmente aberta).

---

### `test_csa_portal.py` — Portal CSA (18 testes)

#### Testes originais do portal

| Teste | O que verifica |
|-------|----------------|
| `test_allowlist_blocks_foreign_url` | URL fora de `csa.uefs.br` levanta `ValueError` |
| `test_fetch_html_converts_and_caches` | HTML é convertido para texto limpo; segunda chamada usa cache |
| `test_search_filters_menu` | `web_csa_search` filtra por `query` e `categoria`; `since` filtra atualizações |
| `test_search_falls_back_to_current_sisu_for_course_queries` | Busca por curso/notas retorna os pontos de entrada atuais do SiSU quando não há match literal |
| `test_fetch_resolves_legacy_sisu_url` | URL legada `/sisu/inicial` é resolvida para o slug vigente do SiSU |
| `test_fetch_marks_portal_not_found_html_as_error` | HTML de “página não encontrada” do portal é tratado como erro, mesmo com HTTP 200 |
| `test_search_fails_loud_on_schema_change` | Mudança de schema do portal gera erro explícito (sem silêncio) |
| `test_tools_for_config` | Conjunto único `[kb_list, kb_read]`; `web_csa_*` só com `CHAT_CSA_PORTAL_TOOLS=1` |
| `test_consumer_tools_are_readonly` | Consumer não recebe ferramentas de filesystem (`read`/`bash`/`write`/`edit`) |
| `test_fetch_pdf_extracts_text_with_python_fallback` | Falha do `pdftotext` aciona fallback `pypdf` com sucesso |
| `test_pdf_extraction_reports_clear_error` | PDF corrompido levanta `RuntimeError` descritivo |
| `test_html_links_preserved_as_markdown` | Links HTML são preservados no formato `[texto](url)` |

#### Testes dos novos campos de metadados

| Teste | O que verifica |
|-------|----------------|
| `test_html_result_has_source_type_and_is_official` | `source_type="html"`; `is_official=True` para URL com `/edital`, `False` para `/inicial` |
| `test_pdf_result_has_source_type_pdf` | `source_type="pdf"` e `is_official=True` para URL de edital em PDF |
| `test_pdf_extraction_status_completed` | Texto ≥ 50 chars → `pdf_extraction_status="completed"` |
| `test_pdf_extraction_status_partial` | Texto < 50 chars → `pdf_extraction_status="partial"` |
| `test_pdf_extraction_status_failed` | Ambos extratores falham → `pdf_extraction_status="failed"` + `text_error` |
| `test_is_official_url_heuristic` | `_is_official_url()` retorna `True`/`False` para 6 URLs de exemplo |

---

### `test_citation_quality.py` — Qualidade de citação (26 testes)

Cobre os 15 cenários obrigatórios do requisito de citações confiáveis.
Usa **respostas simuladas** (strings) e **monkeypatch** no portal — sem LLM real.

| Cenário | Teste(s) | O que verifica |
|---------|----------|----------------|
| **1** | `test_cenario1_uma_afirmacao_uma_fonte` | Resposta direta com 1 afirmação tem seção `Fontes:` e 1 linha de fonte válida |
| **2** | `test_cenario2_multiplas_afirmacoes_fontes_distintas` | 2 afirmações com referências `[1]` e `[2]` apontando para URLs distintas |
| **3** | `test_cenario3_rotulo_sem_trecho_invalido` | Detecta ausência de trecho substantivo na resposta inaceitável; resposta aceitável tem trecho entre aspas |
| **4** | `test_cenario4_fonte_oficial_com_trecho` | Fonte de edital oficial contém trecho verbatim entre aspas |
| **5** | `test_cenario5_precedencia_edital` | Em conflito, resposta menciona "prevalece"; 2 fontes; URL com `/edital` na posição `[1]` |
| **6** | `test_cenario6_fonte_ano_diferente_com_aviso` | Fonte de 2025 gera `[!]` ou aviso "pode não se aplicar" |
| **7** | `test_cenario7_pdf_completo` | `fetch_page` com texto ≥ 50 chars → `pdf_extraction_status="completed"` |
| **8** | `test_cenario8_pdf_parcial` | `fetch_page` com texto < 50 chars → `pdf_extraction_status="partial"` |
| **9** | `test_cenario9_pdf_falhou` | Ambos extratores falham → `pdf_extraction_status="failed"` + `text_error` presente, sem `text` |
| **10** | `test_cenario10_ausencia_de_fontes` | Sem fontes suficientes: `[!]` ou "não foi possível" + seção `Fontes:` presente |
| **11** | `test_cenario11_url_invalida_fora_do_allowlist` | URL fora do allowlist retorna erro descritivo (não exceção não tratada) |
| **11** | `test_cenario11_url_http_error` | HTTP 404 → campo `"error"` com código no resultado |
| **12** | `test_cenario12_compatibilidade_campos_antigos` | 7 campos originais (`url`, `fetched_at`, `content_type`, `content`, `chars`, `cached`, `truncated`) + 2 novos (`source_type`, `is_official`) presentes |
| **13** | `test_cenario13_nao_afirmar_sem_confirmacao` | Sem evidência: `[!]` presente e zero trechos entre aspas longas |
| **14** | `test_cenario14_perguntas_ptbr` ×4 | Perguntas em pt-BR sobre matrícula, chamada, lista de espera e cronograma são reconhecidas e geram resposta no formato correto |
| **15** | `test_cenario15_markdown_valido_frontend` ×8 | 8 formatos de resposta diferentes produzem Markdown balanceado para ReactMarkdown |

---

## Formato de resposta validado pelos testes

Os testes de qualidade de citação verificam que o agente produza respostas
no seguinte formato:

```
"<trecho verbatim da fonte que sustenta a afirmação>" [N]

Fontes:
[1] <Título da fonte> — <URL> (acesso YYYY-MM-DD HH:mm)
[2] <Título da fonte> — <URL> (acesso YYYY-MM-DD HH:mm) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
```

Marcadores especiais:
- `[!]` — afirmação não confirmada por trecho verificado
- `[PDF: completo]` — extração de PDF bem-sucedida (≥ 50 chars)
- `[PDF: parcial]` — extração com texto insuficiente (< 50 chars)
- `[PDF: falhou]` — falha de extração (`text_error` presente)

---

## Resultado esperado

```
========================= 49 passed in 0.63s =========================
```
