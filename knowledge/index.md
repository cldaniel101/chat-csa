# Base de Conhecimento — Chat CSA (SISU/UEFS)

Este é o índice raiz do bundle OKF (Open Knowledge Format) do Chat CSA.
Ele organiza o conhecimento curado sobre o processo seletivo SISU na
Universidade Estadual de Feira de Santana (UEFS).

## Categorias

* [Editais](./editais/index.md) — Documentos normativos oficiais do SISU/UEFS (editais, retificações, complementares).
* [Cronogramas](./cronogramas/index.md) — Datas, prazos e calendários do processo seletivo.
* [Procedimentos](./procedimentos/index.md) — Passos necessários para inscrição, matrícula, lista de espera e demais processos.
* [Modalidades](./modalidades/index.md) — Regras de concorrência: ampla concorrência, cotas e bonificações.
* [Perguntas Frequentes](./perguntas-frequentes/index.md) — Dúvidas comuns de candidatos e respostas curadas.

## Sobre este Bundle

- **Formato:** OKF v0.1 — arquivos Markdown com frontmatter YAML.
- **Fonte única:** Portal CSA/UEFS (`https://csa.uefs.br/`).
- **Versionamento:** Cada alteração é rastreada via `git`; consulte o [log de atualizações](./log.md).
- **Arquitetura:** Bundle OKF curado como fonte única da verdade; consultas diretas aos conceitos e ao portal via ferramentas dedicadas.

## Convenções

1. Todo arquivo de conceito inicia com frontmatter YAML (`type`, `title`, `description`, `resource`, `tags`, `timestamp`).
2. Índices (`index.md`) não possuem frontmatter — servem apenas para navegação (divulgação progressiva).
3. Cross-links usam caminhos relativos ao bundle (ex.: `./procedimentos/matricula-documentos.md`).
4. Citações referenciam URLs oficiais do domínio `csa.uefs.br`.
