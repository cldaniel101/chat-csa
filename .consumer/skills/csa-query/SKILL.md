---
name: csa-query
description: Responde perguntas sobre SISU/UEFS com recuperação do bundle e fallback no portal oficial
allowed-tools: read web_csa_fetch web_csa_search
---

# csa-query — Fluxo de resposta do Consumer

## Fluxo (exemplo real)

Pergunta: *"Quais documentos preciso para matrícula?"* →

1. Bundle local primeiro:
   `read("knowledge/procedimentos/matricula-documentos.md")` (ou navegue
   `knowledge/` a partir de `knowledge/index.md`).
2. Achou resposta completa e atualizada? → responda direto.
3. Não achou, pareceu incompleta ou desatualizada → portal:
   `web_csa_search(query="documentos matrícula")` →
   `web_csa_fetch(url_da_pagina)`; se for PDF,
   `web_csa_fetch(url_do_pdf, extract_text=True)`.
4. Responda extrativo:

```markdown
Para a matrícula você precisa apresentar: <trechos verbatim da fonte>
Fontes: [1] <URL> (acesso 2026-08-22)
Em caso de divergência, prevalece o edital oficial.
```

5. Nada encontrado nem no bundle nem no portal → diga "Não encontrei essa
   informação nas fontes oficiais da CSA/UEFS" e aponte https://csa.uefs.br/.

## Disciplina de citação

- Sempre cite a URL da página/PDF que você realmente leu neste turno.
- Só afirme o que está na fonte; conflito entre fontes = dizer.
- Nunca invente prazos, documentos ou datas.
