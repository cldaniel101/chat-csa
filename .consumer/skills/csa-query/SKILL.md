---
name: csa-query
description: Responde perguntas sobre SISU/UEFS com recuperação do bundle e fallback no portal oficial
allowed-tools: kb_list kb_read
---

# csa-query — Fluxo de resposta do Consumer

## Fluxo (exemplo real)

Pergunta: *"Quais documentos preciso para matrícula?"* →

1. Base remota primeiro:
   `kb_list()` para descobrir os caminhos e `kb_read("perguntas-frequentes/…")`
   para ler o conteúdo (csv/tsv viram tabela; PDFs viram texto; binários avisam
   o tipo).
2. Achou resposta completa e atualizada? → responda direto.
3. Não achou, pareceu incompleta ou desatualizada → **com as ferramentas do
   portal ligadas**, siga a skill `csa-portal-lookup` (busca persistente: várias
   consultas, páginas prováveis e PDFs). Sem o portal, responda com o que a base
   cobre e diga que a informação não está nela — sem inventar.
4. Responda extrativo:

```markdown
Para a matrícula você precisa apresentar: <trechos verbatim da fonte>

Fontes:
[1] Edital SISU/UEFS 2026 — https://csa.uefs.br/... (acesso 2026-08-22 17:30) [PDF: completo]
Em caso de divergência, prevalece o edital oficial.
```

5. Nada encontrado nem na base nem no portal → só então diga "Não encontrei
   essa informação nas fontes oficiais da CSA/UEFS", mas inclua as páginas/PDFs
   efetivamente consultados e aponte https://csa.uefs.br/.

## Busca persistente antes de "não encontrado"

- Liste a base inteira com `kb_list` e leia os arquivos prováveis antes de
  concluir; com o portal ligado, siga também a busca persistente da skill
  `csa-portal-lookup`.
- Para documentação de matrícula, ações afirmativas, indígenas, renda ou vínculo
  de trabalho, procure na base por arquivos e seções relacionadas: `edital`,
  `downloads`, `documentos para matrícula`, `vagas reservadas`, `anexo`.
- Se ainda não encontrou, diga "não encontrei depois de consultar..." e liste
  os caminhos/URLs lidos. Isso é diferente de "não existe".

## Disciplina de citação

### Citação por afirmação (obrigatório)

Para cada afirmação relevante na resposta:

1. Identifique a afirmação **antes** de redigir a frase.
2. Localize o trecho na fonte que comprova diretamente essa afirmação.
3. Verifique se o trecho trata:
   - do mesmo processo seletivo (SISU, ProSel, etc.);
   - do mesmo ano ou edição;
   - da mesma instituição, campus, curso ou modalidade;
   - de período ainda válido (não substituído por edital posterior).
4. Cite o trecho entre aspas antes de incluir a referência numérica `[N]`.
5. Se não houver trecho que comprove a afirmação, use:
   `[!] Não foi possível confirmar esta informação nas fontes consultadas.`

### Rejeição de rótulos como evidência

Não use apenas um nome de seção ou página como evidência suficiente. Exemplos
**inaceitáveis**:

- "Consulte a página Chamada Regular" ← sem informar o que a página estabelece.
- "Veja a Lista de Espera" ← sem apresentar prazo, condição ou regra encontrada.
- "Os documentos estão no portal" ← sem listar os documentos ou citar o trecho.

### Verificação de escopo

Antes de citar uma fonte, confirme:
- A fonte refere-se à **mesma seleção e ano** da pergunta?
- A fonte não foi **substituída** por um edital retificador posterior?
- A fonte é da **mesma instituição** (UEFS/CSA)?

Se a fonte for de ano diferente, sinalize: *"Esta informação é do processo
seletivo de YYYY e pode não se aplicar ao processo atual."*

### Divergência entre fontes

Se duas fontes conflitarem:
1. Apresente os dois trechos.
2. Aplique a regra de precedência: edital oficial > página informativa.
3. Diga explicitamente: *"O edital (fonte [1]) prevalece sobre a página
   informativa (fonte [2]) neste ponto."*

### Conceitos sem `resource:` (upload avulso)

Conceitos criados pelo upload avulso podem não ter `resource:`/`url:` nem a
seção `Citations`. Para eles:

1. Cite pelo **título do conceito + caminho na base** (ex.:
   `[1] Aviso de matrícula — editais/aviso.md`).
2. **Nunca invente uma URL** para o conceito.
3. Na lista final, registre o conceito como título + caminho, sem horário de
   acesso (não houve requisição externa).

### Não reutilize citações

- Não cite uma URL apenas porque pertence ao mesmo site.
- Não misture informações de fontes diferentes sem indicar a composição.
- Se a citação serve para mais de uma afirmação, indique explicitamente qual
  trecho suporta cada afirmação.

## Regras gerais

- Responda diretamente, sem o rótulo `Resposta:`.
- Use Markdown com parcimônia para tornar a resposta mais legível: destaque em
  **negrito** datas, prazos, documentos, modalidades, ações obrigatórias,
  conclusões e ressalvas importantes.
- Quando a resposta tiver uma lista de itens, use bullets curtos e destaque o
  nome do item ou condição em **negrito** antes da explicação.
- Não coloque a referência numérica em negrito. Escreva a citação como [1] ou
  [2] logo após a frase que ela comprova.
- Em saudações, agradecimentos e outras mensagens sociais curtas, não consulte
  fontes e não inclua a seção `Fontes:`.
- Só inclua `Fontes:` quando uma fonte tiver sido efetivamente aberta neste
  turno (`kb_list`/`kb_read` e, com o portal ligado, as ferramentas da skill
  `csa-portal-lookup`).
- Sempre cite a URL da página/PDF que você realmente leu neste turno.
- Só afirme o que está na fonte; conflito entre fontes = dizer.
- Nunca invente prazos, documentos ou datas.
- Data e hora de acesso no formato: `YYYY-MM-DD HH:mm`.
