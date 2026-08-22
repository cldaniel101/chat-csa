---
name: csa-portal-lookup
description: Localiza documentos e dados no portal CSA (listas de aprovados, editais, cronogramas) usando web_csa_search/fetch
allowed-tools: read web_csa_fetch web_csa_search
---

# csa-portal-lookup — Busca de dados direto no portal CSA

Use esta skill quando o usuário pedir dados que exigem ler o portal oficial:
**listas de aprovados/convocados, resultados, cronogramas, editais** — inclusive
buscar um **nome específico** dentro de PDFs de resultado.

Você é somente leitura. Não há `bash`/`grep`: use `web_csa_fetch` (que já
extrai texto de PDF com `extract_text=True`) e filtre o texto você mesmo.

## Fluxo padrão (ex.: "o Pedro foi aprovado no SISU?")

1. **Descubra a seleção**: `web_csa_search(categoria="sisu")` ou
   `web_csa_search(query="sisu")` → anote a URL da seleção
   (ex.: `https://csa.uefs.br/index.php/sisu261/inicial`).
2. **Ache a página de resultados**: faça `web_csa_fetch` nas páginas da
   seleção (`.../{selecao}/primeira`, `/segunda`, `/terceira`, `/regular`,
   `/listaespera`). O texto extraído traz os links em formato markdown:
   `[Resultado Final Geral](https://csa.uefs.br/index.php/download/file/...)`.
3. **Baixe e leia os PDFs**: para cada link de resultado relevante,
   `web_csa_fetch(url_do_pdf, extract_text=True)` → o campo `text` contém o
   conteúdo do PDF. Se vier `text_error`, não afirme conteúdo interno desse
   PDF; registre a limitação e tente outro documento oficial relacionado.
4. **Filtre você mesmo o nome** procurando no texto retornado (leia com
   atenção; nomes vêm em CAIXA ALTA, ex.: "PEDRO SILVA"). Se o PDF vier
   truncado, refaça o fetch do próximo arquivo relacionado.
5. **Responda citando**:
   ```markdown
   Encontrei 2 candidatos com nome "Pedro" na 3ª Chamada - Lista de Espera:
   - PEDRO HENRIQUE ... — Curso X
   Fontes: [1] URL do PDF (acesso YYYY-MM-DD)
   ```

## Dicas

- Links aparecem como `[texto](url)` no conteúdo das páginas HTML — **siga-os**;
  nunca peça URL ao usuário.
- Se uma página não listar o documento esperado, tente as outras páginas da
  seleção (`/regular`, `/primeira`...) ou a página `/downloads`.
- Rate-limit é automático (~3s entre requests): evite baixar dezenas de PDFs
  de uma vez; escolha primeiro o mais provável pelo título do link.
- Se o nome não aparecer, diga onde procurou e sugira verificar chamadas
  adicionais — não afirme aprovação/reprovação sem base.
- `text_error` em PDF significa que a leitura falhou; não trate como lista vazia.
