# ADR-004: Tokens de Deploy Project-Scoped por Projeto

**Data:** 2026-11-09
**Status:** Aceita
**Decisores:** Equipe Chat CSA
**Substitui parcialmente:** [ADR-003](./003-simplificacao-arquitetura-devops.md) (apenas o modelo de credencial de deploy)

---

## 1. Contexto

A [ADR-003](./003-simplificacao-arquitetura-devops.md) unificou o acesso à Vercel num único token de escopo de time, guardado no secret `VERCEL_TOKEN`, com a justificativa de reduzir a esteira a quatro segredos.

Na prática, o token único tem dois problemas:

1. **Raio de dano desnecessário:** um token de time dá permissão de deployment sobre *todos* os projetos do time (inclusive os que não têm relação com o Chat CSA). O pipeline só precisa publicar em dois projetos.
2. **Ciclo de vida opaco:** token da Vercel é *write-only* — o valor aparece uma única vez, na criação, e não pode ser recuperado. Quando o token venceu (novembro de 2026), o deploy passou a falhar com `The token provided via --token argument is not valid` e não havia valor recuperável em lugar algum: era obrigatório criar outro.

Além disso, um token project-scoped **não** expõe `/v2/user`, o que quebra o `vercel alias set` da CLI com `Error: User not found.` — descoberto porque o passo do alias estava protegido por `|| true` e falhava em silêncio.

## 2. Decisão

- O deploy usa **um token project-scoped (`vcp_…`) por projeto**, em dois secrets: `VERCEL_TOKEN_API` (projeto `chat-csa-api`) e `VERCEL_TOKEN_FRONTEND` (projeto `chat-csa-web`).
- O workflow resolve o token por job com `secrets[matrix.token_secret] || secrets.VERCEL_TOKEN`, mantendo `VERCEL_TOKEN` apenas como compatibilidade opcional para quem preferir um token de time. Ele não está cadastrado no repositório.
- O alias estável de preview é aplicado via API (`POST /v2/deployments/{id}/aliases`), e não por `vercel alias set`.
- O passo de alias não engole mais erro: falha vira `::warning::` visível no log e no Step Summary.

## 3. Consequências

**Positivas**

- Cada credencial só pode publicar no projeto a que está restrita.
- Revogar um token não derruba o outro projeto.
- Sem `|| true` escondendo erro, uma falha de alias aparece no log em vez de deixar o preview servindo commit antigo.

**Negativas**

- São 5 segredos em vez de 4, e a rotação é feita projeto a projeto.
- Tokens project-scoped exigem o caminho de API para operações que dependem de contexto de usuário (alias, `whoami`, `project inspect`).

## 4. Alternativas consideradas

- **Manter um token de time (ADR-003):** mais simples, porém com acesso a todos os projetos do time e sem ganho operacional real.
- **Instalar o GitHub App da Vercel:** dispensaria tokens, mas depende de permissão administrativa no repositório GitHub, indisponível para a equipe (motivo original da ADR-003).
