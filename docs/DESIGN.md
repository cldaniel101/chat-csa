---
version: 2.0-extracted
name: CSA UEFS Modern & SISU Design System
description: Sistema de design extraído diretamente dos estilos ativos do portal CSA/UEFS (csa.uefs.br — styles_new.css, inicial_new.css, menu_new.css)
extracted_at: 2026-09-11
source_urls:
  - https://csa.uefs.br/
  - https://csa.uefs.br/index.php/sisu261/inicial
  - https://csa.uefs.br/css/styles_new.css
  - https://csa.uefs.br/css/inicial_new.css
  - https://csa.uefs.br/css/menu_new.css
colors:
  primary: "#a11284"
  primary-light: "#ee5983"
  primary-dark: "#7c0d66"
  gradient-sisu: "linear-gradient(160deg, #ee5983 0%, #a11284 100%)"
  gradient-sisu-hover: "linear-gradient(160deg, #f06a92 0%, #b31694 100%)"
  gradient-menu: "linear-gradient(90deg, rgba(154, 23, 155, 1) 0%, rgba(252, 70, 107, 1) 100%)"
  secondary: "#eb6156"
  tertiary: "#0093e9"
  accent-teal: "#80d0c7"
  surface: "#ffffff"
  surface-subtle: "#fbf6fa"
  neutral-bg: "#f4f7f6"
  on-surface: "#282626"
  on-primary: "#ffffff"
  muted: "#7e7e7e"
  border: "#e5dbe3"
  border-subtle: "#ede4ec"
  border-strong: "#c9b6c5"
  warning: "#ffd15c"
  warning-dark: "#e5b942"
  success: "#2fbf71"
  success-light: "#84fab0"
  error: "#e32d52"
  link: "#a11284"
  link-hover: "#ee5983"
  link-alt: "#0093e9"
typography:
  font-primary: "'Kumbh Sans', 'Nunito Sans', system-ui, -apple-system, sans-serif"
  font-heading: "'Kumbh Sans', 'Roboto', sans-serif"
  font-body: "'Nunito Sans', 'Open Sans', sans-serif"
  headline-lg:
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.25
  headline-md:
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.3
  headline-sm:
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.35
  body-md:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  label-md:
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0.02em
  caption:
    fontSize: 11.5px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  panel: 14px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
elevation:
  shadow-sm: "0 2px 4px rgba(0, 0, 0, 0.05)"
  shadow-card: "0 4px 12px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04)"
  shadow-panel: "0 14px 38px rgba(161, 18, 132, 0.18), 0 4px 12px rgba(0, 0, 0, 0.08)"
  shadow-launcher: "0 8px 24px rgba(161, 18, 132, 0.32)"
  shadow-focus: "0 0 0 3px rgba(238, 89, 131, 0.35)"
components:
  launcher:
    background: "{colors.gradient-sisu}"
    color: "{colors.on-primary}"
    rounded: "{rounded.full}"
    shadow: "{elevation.shadow-launcher}"
  panel:
    background: "{colors.surface}"
    border: "1px solid {colors.border}"
    rounded: "{rounded.panel}"
    shadow: "{elevation.shadow-panel}"
  header:
    background: "{colors.gradient-sisu}"
    color: "{colors.on-primary}"
    borderBottom: "1px solid rgba(255, 255, 255, 0.18)"
  button-primary:
    background: "{colors.gradient-sisu}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    hoverBackground: "{colors.gradient-sisu-hover}"
  button-destaque:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.sm}"
  input:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
---

# CSA UEFS Modern & SISU Design System

## 1. Origem e Metodologia de Extração

Este design system foi extraído diretamente das folhas de estilo ativas e páginas de produção do portal da Coordenação de Seleção e Admissão da Universidade Estadual de Feira de Santana (**CSA/UEFS**, `https://csa.uefs.br`):

- `styles_new.css`: estilos estruturais, cards, tipografia base e componentes de navegação;
- `inicial_new.css`: paleta de categorias, banners e temas específicos de processos seletivos;
- `menu_new.css`: degradês modernos, menus interativos e cabeçalho com transições;
- `sisu261_inicial.html`: layout de produção da área oficial do SiSU na UEFS.

## 2. Identidade Visual do SiSU/CSA

Diferente do portal legado com verde/laranja genéricos, a área moderna do **SiSU na CSA/UEFS** possui uma identidade forte e contemporânea:

1. **Gradiente Assinatura SiSU:** transição linear marcante entre o rosa/coral vivo (`#ee5983`) e o magenta intenso (`#a11284`). Presente nos banners de destaque, badges e cabeçalhos de processo seletivo.
2. **Superfícies de Conteúdo Claras:** fundo geral neutro e suave (`#f4f7f6`), com cartões e blocos informativos em branco puro (`#ffffff`) delimitados por bordas sutis em tons rosados suaves (`#e5dbe3`).
3. **Cores de Sinalização:**
   - **Aviso e Disponibilidade:** amarelo ouro/âmbar (`#ffd15c` / `#fcd04b`), extraído de `.message-menor.alert`.
   - **Sucesso e Validação:** verde vivo (`#2fbf71` / `#06d6a0`).
   - **Erro e Bloqueio:** vermelho coral (`#e32d52`).
   - **Ações e Destaques Secundários:** azul ciano (`#0093e9`) e coral (`#eb6156` de `.botaoDestaque`).

## 3. Tipografia

- **Famílias:** `"Kumbh Sans"`, `"Nunito Sans"` e `"Roboto"`, com fallback para sans-serif do sistema.
- **Hierarquia:**
  - Títulos: `"Kumbh Sans"`, pesos 600 e 700, espaçamento equilibrado.
  - Corpo e Leitura: `"Nunito Sans"` ou `"Open Sans"`, 13.5px a 14px, entrelinha 1.5 a 1.55.
  - Textos Auxiliares e Metadados: 11.5px a 12px, cor atenuada (`#7e7e7e`).

## 4. Formas, Bordas e Elevação

- **Raios de Borda (Border Radius):**
  - Painel principal e banners: `14px` (padrão de `.banner` e `.container-categoria-selecao`).
  - Balões de mensagem e cartões: `10px` a `12px`.
  - Botões de ação, inputs e chips: `6px` a `8px`.
  - Botão flutuante (launcher), avatares e indicadores de status: `9999px` (circular / pílula).
- **Elevação e Sombras:**
  - Sombras suaves com tom magenta atenuado (`rgba(161, 18, 132, 0.18)`), gerando sensação de profundidade moderna sem poluição visual.

## 5. Diretrizes para o Widget de Chat Flutuante

- **Botão Flutuante (Launcher):** gradiente oficial SiSU (`#ee5983` → `#a11284`), borda branca fina de 2px, sombra elevada de destaque com leve halo magenta.
- **Cabeçalho do Chat:** gradiente oficial SiSU, texto em branco com alto contraste, indicador de disponibilidade com ponto dourado/verde (`#ffd15c`/`#2fbf71`), botões de ação translúcidos.
- **Mensagem do Usuário:** fundo com gradiente sutil SiSU ou magenta (`#a11284`), texto em branco, alinhado à direita com canto inferior direito reto.
- **Mensagem do Assistente:** fundo branco sobre superfície sutil (`#fbf6fa`), borda leve (`#e5dbe3`), texto escuro (`#282626`), citações oficiais em magenta e links em azul/magenta.
- **Sugestões e Chips:** cartões brancos com borda rosa suave (`#ee5983` a 40%), hover com preenchimento em tom pastel (`#fbf6fa`) e borda magenta ativa.
- **Composer / Caixa de Entrada:** fundo branco, borda sutil, foco com anel suave rosa/magenta, botão de envio com gradiente SiSU.
