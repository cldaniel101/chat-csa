---
name: name-lookup-in-lists
description: Busca um nome específico em listas de aprovados/convocados do portal CSA (PDFs de resultado)
allowed-tools: read web_csa_fetch web_csa_search
---

# name-lookup-in-lists — Procurar nome em listas de resultado

Use quando o usuário perguntar se uma **pessoa específica** foi aprovada,
convocada ou está em lista de espera.

## Fluxo (exemplo real)

Pergunta: *"Me diga se algum Pedro foi aprovado no último SISU"* →

1. Descobrir a seleção:
   `web_csa_search(categoria="sisu")` → URL da seleção
   (`https://csa.uefs.br/index.php/sisu261/inicial`).
2. Ler as páginas de resultado (uma por vez):
   `web_csa_fetch("https://csa.uefs.br/index.php/sisu261/regular")`
   O texto traz os links em formato markdown, ex.:
   `[Resultado Final Geral (Sexta Retificação)](https://csa.uefs.br/index.php/download/file/sisu261/..._resultado_geral_final...)`
3. Baixar e ler o PDF mais provável pelo título do link:
   `web_csa_fetch(url_do_pdf, extract_text=True)` → campo `text` tem o conteúdo.
   Se vier `text_error`, não considere a lista lida; informe a limitação e tente
   outro PDF oficial relacionado.
4. Procurar o nome no texto retornado (nomes vêm em CAIXA ALTA,
   ex.: "PEDRO SILVA"; busque também variantes sem acento).
5. Responder citando:

```markdown
Encontrei 2 candidatos com nome "Pedro" na Chamada Regular:
- PEDRO HENRIQUE ... — Matemática [Ampla Concorrência]
Fontes: [1] <URL do PDF> (acesso 2026-08-22)
```

## Regras

- **Nunca peça URL ao usuário** — descubra você seguindo os links.
- Se o nome não estiver na lista lida, diga onde procurou e responda
  "não encontrei nesta lista" — nunca afirme aprovação/reprovação sem base.
- `text_error` em PDF significa falha de extração, não ausência do nome.
- Evite baixar muitos PDFs seguidos (rate-limit ~3s); escolha pelo título.
