# Design system

Este documento descreve a identidade visual usada pelo Chat CSA, como os tokens do design system são implementados no frontend e quais regras valem para novas telas. O arquivo autoritativo de tokens é o `docs/DESIGN.md` — ele é a fonte, este documento é o guia de uso.

## Resumo para não-devs

O chat foi desenhado para "parecer parte do portal da CSA": em vez de cores genéricas, ele reutiliza a identidade visual da área do SiSU na UEFS — o degradê rosa/coral para magenta, o mesmo par de fontes e os mesmos cartões claros com bordas rosadas. Quem abre o widget na página da universidade reconhece o visual como oficial. Todo o esquema está catalogado como um conjunto de "tokens" (cores, fontes, cantos, sombras) para que qualquer tela nova saia consistente sem reinventar estilo.

## Origem e status

`docs/DESIGN.md` é um arquivo **autoral** (`version: 2.0-extracted`), extraído em 2026-09-11 diretamente das folhas de estilo do portal (`styles_new.css`, `inicial_new.css`, `menu_new.css`) e do layout de produção do SiSU. Ele é citado, nunca reescrito; os valores abaixo são um resumo de leitura.

## Tokens principais

| Grupo | Valores |
|---|---|
| Marca | `primary #a11284`, `primary-light #ee5983`, `primary-dark #7c0d66` |
| Gradiente assinatura | `linear-gradient(160deg, #ee5983 0%, #a11284 100%)` (hover `#f06a92 → #b31694`) |
| Secundárias | `secondary #eb6156`, `tertiary #0093e9`, `accent-teal #80d0c7` |
| Superfícies | `surface #ffffff`, `surface-subtle #fbf6fa`, `neutral-bg #f4f7f6` |
| Texto | `on-surface #282626`, `on-primary #ffffff`, `muted #7e7e7e` |
| Bordas | `border #e5dbe3`, `border-subtle #ede4ec`, `border-strong #c9b6c5` |
| Sinalização | `warning #ffd15c`, `success #2fbf71`, `error #e32d52` |
| Links | `link #a11284`, `link-hover #ee5983`, `link-alt #0093e9` |
| Tipografia | títulos em `Kumbh Sans` (600/700); corpo em `Nunito Sans`/`Open Sans` (13–14px, linha 1.5–1.55); auxiliares 11.5–12px |
| Formas | `sm 4px`, `md 8px`, `lg 12px`, `panel 14px`, `full 9999px` |
| Espaçamento | `xs 4px`, `sm 8px`, `md 12px`, `lg 16px`, `xl 24px` |
| Elevação | sombras suaves com halo magenta (`shadow-panel: 0 14px 38px rgba(161,18,132,.18)`), foco `0 0 0 3px rgba(238,89,131,.35)` |

## Implementação no frontend

`frontend/src/index.css` traduz o DESIGN.md para CSS custom properties (`--c-primary`, `--c-gradient-sisu`, `--radius-panel`, `--shadow-panel`, …) e importa as três famílias do Google Fonts. O mesmo arquivo expõe **aliases funcionais** (`--bg`, `--surface`, `--border`, `--text`, `--accent`, `--radius`, `--sans`) que os componentes usam.

`frontend/src/components/chat/CSAChatWidget.css` consome exclusivamente os tokens: o launcher usa `--c-gradient-sisu` + `--shadow-launcher` + `--radius-full`; o painel usa `--c-surface` + `--c-border` + `--radius-panel` + `--shadow-panel`; o composer e os chips usam `--radius-md` e o anel de foco `--shadow-focus`.

## Componentes do widget

- **Launcher**: circular, gradiente SiSU, borda branca de 2px e `--shadow-launcher`; rótulos de acessibilidade (`aria-label`, `aria-expanded`).
- **Header**: gradiente, título "Assistente CSA", indicador de disponibilidade (`ok`/`off`/`checking`) com ponto colorido e texto só para leitor de tela (`csa-sr-only`).
- **Mensagens**: usuário alinhado à direita em rosa; assistente em cartão branco com borda sutil; bloco de fontes separado, com chips de citação `[N]` renderizados como `<sup>` e lista de fontes em cartões.
- **Status do agente**: linha com `role="status"` e `aria-live="polite"` que muda conforme o passo (ex.: "Acessando portal", "Acessando PDF").
- **Sugestões**: cartões clicáveis exibidos no estado vazio.
- **Aviso fixo**: o widget sempre mostra o aviso de que o chatbot pode errar e que as fontes oficiais prevalecem.

## Embed e responsividade

`frontend/public/embed.js` cria um iframe isolado (sem conflito de CSS com a página hospedeira). Fechado, o iframe tem 96×96px; aberto, cresce até 432px de largura por 720px de altura, respeitando a viewport. O posicionamento vem dos atributos `data-position` (right/left), `data-bottom`, `data-side`, `data-z-index` e `data-title`; o estado aberto/fechado é comunicado por `postMessage` (`source: "chat-csa"`, `type: "csa-chat:state"`). Em `?embed=1`, o `App.tsx` remove o fundo mock e deixa a página transparente.

## Questão em aberto

`frontend/src/App.css` usa `color: var(--c-on-accent)` em `.btn`, mas `--c-on-accent` não é definida em `index.css` nem em outro arquivo do frontend — o token mais próximo é `--c-on-primary`. A cor do texto desse botão depende hoje do valor herdado; a correção é definir o alias ou trocar a referência.

## Fontes

- `docs/DESIGN.md` (autoral — fonte dos tokens)
- `frontend/src/index.css`
- `frontend/src/App.css`
- `frontend/src/components/chat/CSAChatWidget.css`, `ChatHeader.tsx`, `ChatStatus.tsx`, `ChatSuggestions.tsx`
- `frontend/public/embed.js`
