# Testes

Este documento descreve a estratégia de testes do Chat CSA: o que cada arquivo cobre, como rodar a suíte localmente e quais garantias os testes dão antes de mexer no servidor, no portal ou nos prompts.

## Princípios

A suíte é **offline e determinística**: nenhum teste faz requisição real ao portal nem chama LLM de verdade. Onde o LLM é necessário, o provedor `fake` é ativado por `LLM_PROVIDER=fake` (implementado em `agent/factory.py`); onde o portal é necessário, as respostas são simuladas com `monkeypatch`. Assim a suíte roda em CI ou na máquina do contribuidor sem rede e sem credenciais.

## Como rodar

```bash
make test                            # uv run pytest -v
uv run pytest tests/ -v              # equivalente
uv run pytest tests/test_server.py -v
uv run pytest tests/ -k test_cenario5
```

Lint e formatação (mesma configuração usada pelo CI):

```bash
make lint      # uv run ruff check src
make format    # uv run ruff check --fix src
```

O `tests/README.md` traz o guia de execução detalhado e mostra a saída esperada da suíte; a contagem cresce a cada novo caso.

## Estrutura da suíte

| Arquivo | Foco | Exemplos de caso |
|---|---|---|
| `tests/test_tools.py` | ferramentas básicas do agente | ciclo `write`→`read`→`edit`, execução de `bash`, composição do prompt a partir de `AGENTS.md` + skills |
| `tests/test_server.py` | API FastAPI | `/health`, `/v1/models`, completions non-stream e stream (SSE com `[DONE]`), injeção da FAQ curada no prompt, shim `/api/chat` |
| `tests/test_csa_portal.py` | cliente do portal | allowlist bloqueia domínio externo, cache de fetch, busca com filtros, fallback para o SiSU vigente, links markdown, extração de PDF e status `completed`/`partial`/`failed` |
| `tests/test_qa_cache.py` | recuperação da FAQ | parsing de Markdown (frontmatter + entradas), ranking por similaridade, entradas `dynamic` não dão short-circuit, formatação sem URL omite a linha de fonte |
| `tests/test_response_quality.py` | formatação da resposta | rótulo `Resposta:` removido, nota de divergência órfã removida, seção `Fontes:` preservada, `_has_source_lookup` exige fonte realmente aberta |
| `tests/test_citation_quality.py` | qualidade de citação | 15 cenários obrigatórios (fonte única, múltiplas fontes, trecho verbatim, precedência do edital, avisos de ano, PDFs, ausência de fontes, URL inválida, Markdown válido para o frontend) |
| `tests/test_scrape_portal.py` | utilitários de scraping | `slugify` seguro/estável, deduplicação, frontmatter idempotente em `knowledge/raw/` |
| `tests/test_admin.py` | regressão do painel admin | o painel não grava `.sesskey` no cwd (na Vercel `/var/task` é somente leitura); chave do ambiente evita arquivo |

## O contrato de citação sob teste

A parte mais importante da suíte é `test_citation_quality.py`: ela codifica o formato que o consumer deve produzir (também descrito em `tests/README.md` e nas skills `.consumer/`):

```text
"<trecho verbatim da fonte que sustenta a afirmação>" [N]

Fontes:
[1] <Título da fonte> — <URL> (acesso YYYY-MM-DD HH:mm)
[2] <Título da fonte> — <URL> (acesso YYYY-MM-DD HH:mm) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
```

Marcadores verificados: `[!]` para afirmação não confirmada, `[PDF: completo]` (extração com ≥ 50 caracteres), `[PDF: parcial]` (texto insuficiente) e `[PDF: falhou]` (falha de extração). Os cenários cobrem respostas em pt-BR sobre matrícula, chamada, lista de espera e cronograma, além de validar que o Markdown gerado é balanceado para o ReactMarkdown do widget.

## Configuração

`pyproject.toml` define `[tool.pytest.ini_options]` com `asyncio_mode = "auto"` e `testpaths = ["tests"]`, e `[tool.ruff]` com `line-length = 120`, alvo `py310` e as regras `E, F, I, B, C4, UP` (com `E501` ignorado).

## O que o CI roda hoje

O job `checks` do `.github/workflows/deploy.yml` roda **lint e build**, não a suíte pytest: `npm ci`, `npx oxlint src`, `npm run build` no frontend e `ruff check src` no backend. Como os testes são offline e rápidos, rodar `uv run pytest` no job seria o passo natural para transformar a suíte em gate de deploy — hoje ela depende de execução manual local.

## Fontes

- `tests/README.md` e os 8 arquivos de `tests/`
- `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.ruff]`)
- `src/chat_csa/agent/factory.py` (provedor `fake`)
- `.github/workflows/deploy.yml`
