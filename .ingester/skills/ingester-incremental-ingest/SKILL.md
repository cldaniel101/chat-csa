---
name: ingester-incremental-ingest
description: Ingestão incremental das fontes do portal CSA por data — descobre novidades, baixa e atualiza o bundle OKF/BM25
allowed-tools: read write edit bash web_csa_fetch web_csa_search
---

# ingester-incremental-ingest — Ingestão incremental

Use para trazer o bundle em dia sem re-ingestão completa.

## Fluxo (exemplo real)

1. Ler a última data de ingestão:
   `read("knowledge/log.md")` → última entrada `## 2026-08-20`.
2. Descobrir novidades desde então:
   `web_csa_search(since="2026-08-20")` → registros com `updated_at`.
3. Sem novidades → terminar: "bundle já está em dia (fonte: catálogo, acesso
   YYYY-MM-DD)" e registrar a checagem no log.
4. Para cada item novo/alterado:
   - Página: `web_csa_fetch(url)` → texto limpo.
   - PDF: `web_csa_fetch(url_pdf, extract_text=True)` → campo `text`.
     Se vier `text_error`, não crie conceito com conteúdo interno presumido do
     PDF; registre a limitação no log e busque outra fonte oficial.
   - Snapshot cru: `bash("mkdir -p data/raw/2026-08-22 && ...")` com URL+timestamp.
   - Conceito OKF: `write("knowledge/<tema>/<slug>.md", ...)` com frontmatter
     YAML (`type`, `title`, `description`, `resource`, `tags`, `timestamp`).
5. Reconstruir índice BM25 (`data/bm25.db`) conforme skill `csa-ingest`.
6. Registrar no log:

```markdown
## 2026-08-22
- web_csa_search(since=2026-08-20): 3 novidades
- adicionado knowledge/cronograma/sisu261-cronograma.md (resource: <URL>)
```

## Regras

- Nunca use curl/wget direto no portal; só web_csa_fetch/search.
- Um conceito OKF por fonte; valide YAML e cross-links antes de gravar.
- Se `web_csa_search` retornar erro de schema, reporte — não presuma
  "sem atualizações".
