---
name: csa-ingest
description: Ingesta fontes oficiais da CSA/UEFS em um bundle OKF + índice BM25
allowed-tools: read write edit bash
---

# csa-ingest — Skill do Ingester

Ajude o usuário a ingerir e curar fontes da CSA/UEFS.

## Fluxo de trabalho

1. **Descobrir**: `bash("ls -R knowledge 2>/dev/null; cat knowledge/index.md 2>/dev/null | head -n 100")` para ver o bundle existente.
2. **Crawlear**: Rode `bash("python scripts/crawl_csa.py --help 2>&1 | head -n 50")` ou inspecione `scripts/crawl_csa.py`. Faça snapshot em `data/raw/{date}/`.
3. **Rascunhar conceitos**: Para cada nova fonte, `write("knowledge/<area>/<slug>.md", ...)` com frontmatter OKF:
   ```yaml
   ---
   type: Edital | Comunicado | Cronograma | Modalidade | Procedimento | FAQ | Referencia
   title: Título humano
   description: Resumo em uma linha
   resource: https://csa.uefs.br/...
   tags: [matrícula, documentos, ...]
   timestamp: 2025-12-02T18:00:00Z
   ---
   ```
   Corpo: `# Contexto`, `# Conteúdo`, `# Citations` (URLs externas).
4. **Validar**: `bash("python scripts/validate_okf.py knowledge 2>&1 | head -n 100")` ou checagens manuais.
5. **Indexar**: `bash("python scripts/build_index.py --bundle knowledge --out data/bm25.db 2>&1")`
6. **Registrar**: `edit("knowledge/log.md", oldText, newText)` com uma entrada datada.

## Convenções

- Um conceito por arquivo (exceto `index.md` / `log.md`).
- Cross-links: `/procedimentos/...` relativo ao bundle e devem resolver.
- Todo diretório tem `index.md`.
- Mantenha o histórico do git limpo: um commit por lote de ingestão.

## Exemplos de prompts

- "Ingesta o edital mais recente de https://csa.uefs.br/index.php/sisu261/editais"
- "Reconstrua o índice BM25 e mostre os top 3 hits para 'documentos matrícula'"
- "Valide o bundle OKF e corrija links quebrados"