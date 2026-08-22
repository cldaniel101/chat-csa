---
version: alpha
name: CSA UEFS Design System
description: Sistema de design extraído do portal oficial da CSA/UEFS (csa.uefs.br)
colors:
  primary: "#ff7300"
  primary-hover: "#e86800"
  secondary: "#589c36"
  tertiary: "#2d7fef"
  neutral: "#f4f4f2"
  surface: "#ffffff"
  on-surface: "#444444"
  on-primary: "#ffffff"
  muted: "#909090"
  border: "#dddcdc"
  border-strong: "#d4d0c8"
  success: "#63af1b"
  success-dark: "#5faa1a"
  warning: "#f2b100"
  error: "#b31717"
  link: "#393939"
  link-alt: "#0a64a4"
typography:
  headline-lg:
    fontFamily: Open Sans
    fontSize: 30px
    fontWeight: 400
    lineHeight: 1.3
  headline-md:
    fontFamily: MyriadPro-Light
    fontSize: 29px
    fontWeight: 600
    lineHeight: 1.25
  headline-sm:
    fontFamily: Open Sans
    fontSize: 20px
    fontWeight: 500
    lineHeight: 1.4
  body-md:
    fontFamily: Open Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Lato
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  label-md:
    fontFamily: Open Sans
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.04em
  caption:
    fontFamily: Open Sans
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  none: 0px
  sm: 3px
  md: 4px
  lg: 6px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 20px
  xl: 30px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    typography: "{typography.label-md}"
    padding: 5px 10px
  button-secondary:
    backgroundColor: "#e1dfd8"
    textColor: "#5e5e5e"
    rounded: "{rounded.md}"
    typography: "{typography.label-md}"
    padding: 5px 10px
  input:
    backgroundColor: "{colors.surface}"
    textColor: "#555555"
    rounded: "{rounded.sm}"
    typography: "{typography.body-md}"
    padding: 4px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.none}"
    padding: 16px
---

# CSA UEFS Design System

## Overview

Sistema de design extraído do portal oficial da Coordenação de Seleção e Admissão da UEFS (csa.uefs.br). O estilo é institucional e funcional: conteúdo denso sobre superfícies brancas, com o **laranja (#ff7300)** como cor de destaque para interações (hovers, legendas, botões primários e datas de calendário) e o **verde institucional (#589c36)** ligado à marca UEFS. A personalidade é sóbria e informativa — o foco está na legibilidade dos editais, cronogramas e avisos.

## Colors

- **Primary (#ff7300):** laranja de destaque — borda superior do header, hover de links e botões, legendas (`legend`/`.legenda`) e dias ativos do calendário.
- **Secondary (#589c36):** verde institucional da UEFS usado na identidade do header.
- **Tertiary (#2d7fef):** azul de blocos temáticos (ex.: tile "Inscrição").
- **Surface / Neutral:** fundo branco do conteúdo central (960px) sobre um fundo externo texturizado claro.
- **On-Surface (#444444):** texto padrão do corpo.
- **Muted (#909090):** textos auxiliares e rodapé.
- **Link (#393939) / Link-alt (#0a64a4):** links de navegação em cinza-escuro e links de blocos em azul.
- **Success (#63af1b, #5faa1a):** verdes dos tiles de acesso rápido ("Consulte", coluna lateral).
- **Warning (#f2b100) / Error (#b31717):** bordas superiores das mensagens de alerta e erro.

## Typography

Família principal **Open Sans** para corpo e UI; **MyriadPro-Light** em títulos de seção e calendário; **Lato** em links e texto corrido menor. Títulos são discretos (peso normal/500), com hierarquia conduzida mais por caixa-alta e cor do que por peso forte.

## Layout

Conteúdo central fixo de ~960–978px centralizado, com header de 150px e sombra suave delimitando a área branca contra o fundo texturizado. Espaçamento base pequeno (4/8/16px), típico de portal densamente informacional.

## Elevation & Depth

Profundidade por **sombras muito suaves**: `0 0 4px #e1dfd8` no container principal e `0 0 2px #aaa` em focos de inputs. Mensagens de feedback usam borda superior de 4px colorida em vez de sombra.

## Shapes

Cantos levemente arredondados (3–6px) em botões, inputs e datas do calendário; rádios totalmente circulares. Tabelas e cartões são quadrados.

## Components

- **Botão primário:** laranja `#ff7300`, texto branco, caixa-alta, raio 4px (derivado do estado hover de `.myButton`).
- **Botão secundário:** cinza-quente `#e1dfd8` com borda `#d4d0c8` e texto `#5e5e5e`; hover ganha sombra `0 0 6px #555`.
- **Inputs:** fundo branco, borda 1px `#ddd`, padding 4px, foco com sombra sutil.
- **Mensagens (alert/error/info):** bloco claro `#f8f8f8` com faixa superior de 4px (amarelo para alerta, vermelho para erro).
- **Tiles de atalho:** blocos coloridos sólidos (verde `#9ec828`, azul `#2d7fef`, vermelho `#db532d`) com links brancos.
- **Tabelas:** bordas `lightgray`, cabeçalho com fundo `#eee`.

## Do's and Don'ts

- Use o laranja apenas para estados interativos e destaques — nunca como cor de fundo de grandes áreas de leitura
- Mantenha o corpo de texto em cinza-escuro (#444) sobre branco; evite preto puro em parágrafos
- Preserve a área de conteúdo branca delimitada por sombra suave — não use bordas fortes ao redor do container principal
- Não introduza novos tons saturados além dos tiles de atalho existentes
- Mantenha títulos em caixa-alta discreta com peso normal/500, sem exagerar em negrito
