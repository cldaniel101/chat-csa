---
name: csa-query
description: Responde perguntas sobre SISU/UEFS via recuperação OKF + BM25
allowed-tools: read write edit bash
---

# csa-query — Skill do Consumer

Ajude o usuário a obter respostas fundamentadas a partir do bundle de conhecimento.

## Fluxo de trabalho

1. **Entender** a pergunta (identificar a intenção: documentos, prazo, cota etc.).
2. **Recuperar**:
   - `bash("python scripts/query.py \"quais documentos para matrícula\" --k 5 2>&1 | head -n 100")`
   - ou `bash("sqlite3 data/bm25.db \"SELECT concept_id, bm25(...) FROM ...\"")`
   - fallback: `bash("grep -R -n \"matrícula\" knowledge --include=\"*.md\" | head -n 30")`
3. **Abrir hits**: `read("knowledge/procedimentos/matricula-documentos.md")` para os melhores hits.
4. **Responder**: Componha uma resposta extrativa:
   ```markdown
   Resposta curta (2-3 frases) + lista extraída verbatim + Fontes: [1] URL (acesso YYYY-MM-DD)
   ```
5. **Não encontrado**: Se nenhum hit pontuar acima do limite, diga "Não encontrei..." e sugira links de `knowledge/index.md`.

## Convenções

- Cite pelo menos uma URL de `resource` por resposta.
- Inclua o `timestamp` do conceito quando disponível.
- Nunca adicione fatos que não estejam nos conceitos recuperados.

## Exemplos de prompts

- "Quais documentos preciso para matrícula da lista de espera?"
- "Quando sai o resultado da lista de espera?"
- "Explique as cotas de escola pública"