---
name: okf
description: >-
  Use esta skill quando o usuário perguntar sobre o Open Knowledge Format (OKF) do Google,
  quiser criar, ler, melhorar ou consultar um bundle de conhecimento OKF, ou pedir
  a especificação completa do OKF. Esta skill fornece a spec, explica o formato
  e orienta o agente no trabalho com bundles OKF — criar documentos de conceito,
  validar estrutura, interligar conhecimento e construir bases de conhecimento
  legíveis por agentes seguindo o padrão OKF v0.1 do Google.
license: Apache-2.0
metadata:
  author: Google Cloud / Community
  version: "0.1"
  source: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
allowed-tools: Read Write Edit Bash
---

# Skill Open Knowledge Format (OKF)

## Quando usar

- O usuário digita `/skill:okf spec` — retorne o documento completo da especificação OKF.
- O usuário pede para **criar** um bundle OKF — monte um diretório de arquivos markdown com frontmatter YAML.
- O usuário pede para **ler** um bundle OKF existente — percorra e explique sua estrutura e conceitos.
- O usuário pede para **melhorar** ou **corrigir** um bundle OKF — valide conformidade, adicione campos ausentes, corrija cross-links, enriqueça conceitos.
- O usuário pede para **consultar** um bundle OKF — responda perguntas navegando no grafo de conhecimento pelos cross-links.
- O usuário pergunta "o que é OKF", "explique OKF", "como funciona OKF" — forneça contexto sobre o formato.
- O usuário menciona "LLM Wiki", "wiki do Karpathy", "knowledge bundle", "OKF" em qualquer contexto.

## Como usar esta skill

A skill OKF funciona em dois modos:

### Modo 1: `/skill:okf spec` — Retornar a especificação completa

Quando o usuário digitar explicitamente `/skill:okf spec`, abra imediatamente e
retorne a especificação completa do OKF de `references/okf-spec.md`. Apresente-a
verbatim ou em um bloco de código bem formatado. Nenhum comentário adicional é
necessário, a menos que o usuário faça perguntas de acompanhamento.

### Modo 2: Ações inferidas (sem prefixo de comando)

Quando o usuário NÃO usa `/skill:okf spec`, infira o que ele quer com base no prompt:

| Intenção do usuário | O que fazer |
|---------------------|-------------|
| **Criar** um novo bundle OKF | Monte um diretório de arquivos markdown com frontmatter YAML. Pergunte sobre domínio, conceitos e relacionamentos. Gere `index.md`, arquivos de conceito e `log.md`. |
| **Ler** / explorar um bundle | Dado um caminho, leia o `index.md` para descobrir a estrutura e depois percorra os cross-links. Resuma o grafo de conhecimento. |
| **Melhorar** / corrigir um bundle | Valide a conformidade (frontmatter, campo `type`, cross-links). Adicione campos ausentes, corrija links quebrados, enriqueça descrições, gere `index.md` se faltar. |
| **Consultar** um bundle | Dada uma pergunta, navegue pelo bundle OKF via arquivos de índice e cross-links para encontrar conceitos relevantes. Sintetize uma resposta com citações a documentos de conceito específicos. |
| **Explicar** OKF | Forneça uma visão geral: o formato, a conexão com o LLM Wiki do Karpathy, os três princípios de design e como se compara ao RAG. Use `references/` como material de origem. |

## O formato OKF (referência rápida)

Um **bundle** OKF é um diretório de arquivos `.md`. Cada arquivo = um **conceito**.

```
my-bundle/
├── index.md          # Opcional: listagem do diretório para navegação do agente
├── log.md            # Opcional: histórico cronológico de mudanças
├── tables/
│   ├── index.md
│   ├── orders.md
│   └── customers.md
└── metrics/
    └── weekly_active_users.md
```

Cada arquivo de conceito tem frontmatter YAML + corpo markdown:

```yaml
---
type: BigQuery Table       # OBRIGATÓRIO — o único campo obrigatório
title: Orders              # Nome de exibição opcional
description: One row per completed customer order.  # Resumo opcional
resource: https://...      # URI opcional para o ativo subjacente
tags: [sales, revenue]     # Lista opcional para categorização
timestamp: 2026-05-28T14:30:00Z  # ISO 8601 opcional
---

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `id`   | STRING | Unique identifier. |

# Joins

Joined with [customers](/tables/customers.md) on `customer_id`.
```

**Regras-chave:**
- `type` é o ÚNICO campo de frontmatter obrigatório
- Cross-links usam markdown padrão `[texto](/caminho/para/conceito.md)` — relativo ao bundle (`/`) ou relativo (`./`)
- Dois nomes de arquivo reservados: `index.md` (divulgação progressiva), `log.md` (histórico de mudanças)
- Links quebrados são tolerados (podem representar conhecimento ainda não escrito)
- Consumidores devem tolerar tipos desconhecidos, campos opcionais ausentes e chaves de frontmatter não reconhecidas

**Três princípios de design:**
1. **Minimamente opinativo** — apenas `type` é obrigatório; o modelo de conteúdo é do produtor
2. **Independência produtor/consumidor** — um bundle escrito por um LLM pode ser consumido por outro LLM
3. **Formato, não plataforma** — sem SDK proprietário, runtime ou conta obrigatórios

## Criando um bundle OKF (passo a passo)

Quando o usuário quiser **criar** um novo bundle:

1. **Pergunte sobre o domínio** — qual sistema, projeto ou área de conhecimento cobre?
2. **Identifique os conceitos** — quais são as entidades-chave (tabelas, métricas, APIs, playbooks, datasets, serviços)? Liste-as.
3. **Defina os relacionamentos** — como os conceitos se relacionam? (tabelas se juntam, métricas dependem de tabelas, playbooks referenciam sistemas)
4. **Monte o diretório** — crie subdiretórios para cada categoria, com arquivos `index.md`
5. **Escreva os arquivos de conceito** — cada um ganha `type`, `title`, `description` e corpo relevante
6. **Interligue** — adicione links markdown entre conceitos relacionados
7. **Adicione `index.md`** na raiz e em cada subdiretório para divulgação progressiva
8. **Adicione `log.md`** na raiz para histórico de mudanças
9. **Valide** — garanta que todo arquivo de conceito tenha campo `type` e frontmatter válido

## Lendo e consultando um bundle OKF

Quando o usuário pedir para **ler** ou **consultar** um bundle:

1. Comece no `index.md` da raiz para descobrir a estrutura de alto nível
2. Siga os cross-links progressivamente — leia os conceitos relevantes
3. Construa um modelo mental do grafo de conhecimento
4. Responda perguntas rastreando links entre conceitos
5. Cite documentos de conceito específicos e seus campos de frontmatter

## Melhorando um bundle OKF existente

Quando o usuário pedir para **melhorar** ou **corrigir** um bundle:

1. **Verifique a conformidade:** todo `.md` não reservado deve ter frontmatter com `type` não vazio
2. **Verifique os arquivos de índice:** cada subdiretório tem `index.md` para divulgação progressiva?
3. **Verifique os cross-links:** há links quebrados? Conceitos órfãos sem links de entrada?
4. **Enriqueça descrições:** os campos `title` e `description` estão presentes e fazem sentido?
5. **Verifique os timestamps:** os campos `timestamp` estão presentes e em ISO 8601?
6. **Gere artefatos ausentes:** crie `index.md`, `log.md`, adicione tags, corrija links

## Fontes

Material de referência detalhado está disponível no subdiretório `references/`:

- `references/okf-spec.md` — Especificação completa do OKF v0.1 (autoritativa)
- `references/karpathy-llm-wiki.md` — O gist original do LLM Wiki de Andrej Karpathy
- `references/google-cloud-announcement.md` — Resumo do post de lançamento do Google Cloud
- `references/community-guide.md` — Guia prático de uso, FAQ e comparações