# ADR-002: Base de Conhecimento em Branch Órfão `data` (Desacoplamento Conteúdo × Código)

**Data:** 2026-09-26  
**Status:** Aceita  
**Decisores:** Equipe Chat CSA (Cláudio, Davi, Paulo)  
**Substitui:** [ADR-001](001-versionamento-base-conhecimento.md)

---

## Contexto

A ADR-001 versionava o bundle OKF em `knowledge/` no próprio branch de código. Na prática, isso acoplou **conteúdo** e **deploy**: o filesystem da Vercel é somente leitura e efêmero, então publicar qualquer ajuste na base exigia um deploy novo — e o agente ingester escrevia nesse filesystem, o que não funcionava em produção (a ferramenta `bash` não tinha uso real).

Além disso, o bundle construído até aqui foi considerado mal construído pela equipe: a decisão é **reiniciar a base do zero**, com o time reenviando o conteúdo — sem migração automática.

## Decisão

1. **Branch órfão `data`**: a base vive num branch sem ancestral comum com os branches de código, com o bundle na raiz e um `README.md` explicando o fluxo. Nenhum código é compartilhado.
2. **Leitura em runtime**: o servidor lê a base pela **GitHub Contents/Git Data API** (backend `github`), com **cache TTL em memória** por instância (padrão 60s), invalidado no upload bem-sucedido. Nada é gravado em disco no deploy.
3. **Escrita por upload admin**: `POST /kb/upload` (multipart em lote, auth admin + `KB_WRITE_TOKEN`) grava **um commit atômico por lote** via Git Data API — nunca deixa lote parcial. O upload sobrescreve sempre, sem trava por sha.
4. **Um único agente (consumer)** com `kb_list`/`kb_read` (leitura, `KB_TOKEN`). As ferramentas `web_csa_*` permanecem no código, desligadas por padrão (`CHAT_CSA_PORTAL_TOOLS=0`). O agente não recebe credencial de admin nem alcança `write()`/`/kb/*`.
5. **Fonte única configurável por ambiente**: `KB_BACKEND=github|local`, `KB_REPO`, `KB_BRANCH`, `KB_ROOT`, `KB_TOKEN`, `KB_WRITE_TOKEN`, `KB_CACHE_TTL`, `KB_LOCAL_PATH`. O backend `local` serve dev/testes; `knowledge/` é gitignored e nunca versionada.
6. **Upload sem validação de formato por enquanto** (qualquer arquivo); a conversão por tipo (csv → tabela, pdf → texto, binário → aviso) acontece só na leitura.

## Alternativas Consideradas

| Alternativa | Por que foi rejeitada |
|---|---|
| **Manter na branch de código (ADR-001)** | Publicar conteúdo continuaria exigindo deploy; conteúdo e código ficam acoplados. |
| **Repositório separado** | Fragmenta o projeto; permissões, CI e onboarding duplicados; histórico de conteúdo descolado do código. |
| **Git submodule / Git LFS** | Complexidade desnecessária para o volume atual; PRs cruzados; LFS é para binários grandes. |
| **Banco/objeto externo (S3, DB)** | Nova infraestrutura e credenciais para o MVP; o Git já entrega histórico e auditoria. |
| **Serviço de CMS** | Custo operacional e de integração; o fluxo de upload admin cobre o caso. |

## Consequências

### Positivas

- **Conteúdo sem deploy:** o time publica pelo endpoint; o chat reflete após o TTL do cache.
- **Auditoria nativa:** cada upload é um commit no branch `data` (`git log`, `git blame`, sha do commit na resposta).
- **Menor privilégio:** leitura (`KB_TOKEN`) e escrita (`KB_WRITE_TOKEN`) separadas; o agente só lê.
- **Código e conteúdo evoluem independentes** — o branch de deploy não carrega a base.
- **Sem escrita em disco no deploy** — compatível com o filesystem somente leitura da Vercel.

### Negativas (e mitigações)

- **Latência do cache:** uma leitura pode servir conteúdo antigo por até `KB_CACHE_TTL` (padrão 60s). Mitigação: o upload invalida as entradas afetadas.
- **Base reinicia do zero:** sem migração automática — decisão explícita do time; o conteúdo é reenviado pelo upload.
- **Upload sem validação:** qualquer arquivo é aceito por ora; validações virão em passos futuros.
- **Teto de corpo da Vercel (~4.5 MB):** lotes maiores precisam ser fatiados pelo cliente (fora do escopo atual).

## Referências

- `ignore/refactor-knowledge.pseudo` — especificação do refactor
- [ADR-001](001-versionamento-base-conhecimento.md) — substituída por esta decisão
- `docs/arquitetura.md`, `docs/api.md`, `docs/deploy.md`, `docs/seguranca.md`
- `src/chat_csa/kb.py`, `src/chat_csa/server/kb_api.py`
