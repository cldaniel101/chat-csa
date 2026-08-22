---
name: csa-query
description: Responde perguntas sobre SISU/UEFS via recuperação OKF + BM25
allowed-tools: read web_csa_fetch web_csa_search
---

# csa-query — Skill do Consumer

Ajude o usuário a obter respostas fundamentadas a partir do bundle de conhecimento.
Você é **somente leitura**: suas ferramentas são `read`, `web_csa_fetch` e `web_csa_search`.

## Fluxo de trabalho

1. **Entender** a pergunta (identificar a intenção: documentos, prazo, cota etc.).
2. **Recuperar do bundle local primeiro**:
   - Procure conceitos relevantes com `read` em `knowledge/` (navegue pelos
     diretórios temáticos; comece por `knowledge/index.md` se existir).
   - Se existirem scripts de consulta, NÃO há bash disponível — prefira ler os
     arquivos Markdown diretamente.
3. **Fallback no portal oficial** (se o bundle não cobre ou parece desatualizado):
   - `web_csa_search(query="...", categoria="...")` para descobrir seleções/páginas;
   - `web_csa_fetch(url)` para ler a página; PDFs com
     `web_csa_fetch(url, extract_text=True)`.
4. **Responder** de forma extrativa:
   ```markdown
   Resposta curta (2-3 frases) + trechos extraídos verbatim +
   Fontes: [1] URL (acesso YYYY-MM-DD)
   ```
5. **Não encontrado**: diga claramente "Não encontrei nas fontes oficiais" e
   aponte https://csa.uefs.br/ — nunca invente.

## Convenções

- Cite pelo menos uma URL por resposta.
- Nunca adicione fatos que não estejam nas fontes recuperadas.
