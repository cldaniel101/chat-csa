# ADR-001: Versionamento Direto da Base de Conhecimento (Bundle OKF)

**Data:** 2026-08-26  
**Status:** Aceita  
**Decisores:** Equipe Chat CSA (Cláudio, Davi, Paulo)

---

## Contexto

O Chat CSA utiliza um bundle de conhecimento no formato OKF (Open Knowledge Format) como **fonte única da verdade** para responder perguntas sobre o SISU/UEFS. Esse bundle consiste em arquivos Markdown com frontmatter YAML, organizados em `knowledge/`.

Até este momento, o `.gitignore` do projeto ignorava a pasta `knowledge/`, o que impedia:

- **Auditabilidade:** Sem histórico Git, não era possível rastrear quem alterou qual conceito e quando.
- **Reprodutibilidade:** Novos membros da equipe precisariam obter o bundle por meios alternativos (download manual, script externo, etc.).
- **Revisão de PRs:** Alterações no bundle não passavam por code review.
- **Rastreabilidade por resposta:** O sistema deve vincular cada resposta a um `concept_id + git sha`; sem versionamento, isso é impossível.

Esses problemas contradizem diretamente os princípios do OKF (versionável, auditável, `git clone`-ável) e os requisitos de fidelidade do projeto (`README.md §79-80`).

## Decisão

**Versionar a pasta `knowledge/` diretamente no repositório principal (`git`).**

Concretamente:

1. Remover toda menção a `knowledge/` do `.gitignore`.
2. Tratar `knowledge/` como código-fonte — sujeito a `git add`, `git diff`, pull requests e code review.
3. Manter o `knowledge/log.md` como registro cronológico complementar ao `git log`.

## Alternativas Consideradas

| Alternativa | Por que foi rejeitada |
|---|---|
| **Git submodule** | Complexidade desnecessária para o MVP; dificulta onboarding de novos devs; PRs cruzados entre repos. |
| **Git LFS** | Arquivos Markdown são texto puro e leves; LFS é projetado para binários grandes — overhead injustificado. |
| **Repositório separado** | Fragmenta o projeto; exige sincronização manual; impede CI unificado. |
| **Download via script** | Quebra a reprodutibilidade; exige infraestrutura extra; não garante versão específica. |
| **Manter ignorado** | Impede auditoria, violando os princípios de design do bundle OKF (versionável e auditável). |

## Consequências

### Positivas

- **Onboarding instantâneo:** `git clone` entrega o projeto completo com a base mínima funcional — zero dependências extras.
- **Auditoria nativa:** `git blame`, `git log` e `git diff` sobre qualquer conceito.
- **Code review:** Alterações no bundle passam por PR, garantindo revisão humana (conforme fluxo OKF §5.5).
- **CI/CD integrado:** Validação do bundle (frontmatter, links, domínio de `resource`) pode rodar no mesmo pipeline do código.
- **Reprodutibilidade por sha:** Cada resposta pode citar o `git sha` do bundle usado, tornando-a verificável.

### Negativas (e mitigações)

- **Tamanho do repositório:** O bundle crescerá com novos conceitos. Mitigação: para o MVP (~200-500 conceitos, ~1-2 MB de Markdown), o impacto é negligível. Se ultrapassar ~50 MB, reavaliar com Git LFS ou submodule (ADR futura).
- **Ruído em diffs:** PRs com muitos conceitos podem ser verbosos. Mitigação: separar PRs de bundle (prefixo `knowledge:`) de PRs de código.

## Referências

- [knowledge/index.md](../../knowledge/index.md) — Índice raiz do bundle
- [knowledge/log.md](../../knowledge/log.md) — Log de alterações do bundle
