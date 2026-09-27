# Arquitetura

Este documento explica como o Chat CSA funciona por dentro: onde vive a informação, como ela chega até o agente e por que o projeto trocou RAG por uma base de conhecimento curada. A primeira seção é um resumo legível sem conhecimento técnico; as seguintes descem ao detalhe.

## Resumo para não-devs

A base de conhecimento do Chat CSA vive num **branch separado do próprio repositório** (o branch `data`), fora do código. O time envia os arquivos pelo endpoint de upload (`/kb/upload`, com login admin); o servidor converte cada um num conceito OKF e grava tudo num único commit atômico. Em runtime, o **consumer** — o único agente — lê essa base pela API do GitHub, com cache em memória, e responde citando sempre a URL oficial de cada fonte. Quando não encontra a resposta, o sistema foi projetado para dizer que não encontrou — em vez de inventar. O site do chat é um botão flutuante que pode ser embutido na página da CSA.

## Visão em camadas

```text
Fontes oficiais da CSA/UEFS (portal csa.uefs.br, PDFs)
        ↓  time (curadoria humana) → POST /kb/upload (auth admin, conversão em OKF)
Base de conhecimento remota (branch órfão `data`, bundle OKF na raiz)
        ↓  consumer: kb_list/kb_read (GitHub API + cache TTL em memória)
Resposta extrativa com citações (Fontes: com URL e horário de acesso)
        ↓
Usuário (widget React embutível / API OpenAI-compatible)
```

O portal continua acessível como fonte complementar: com `CHAT_CSA_PORTAL_TOOLS=1`, o consumer também recebe `web_csa_fetch`/`web_csa_search` (allowlist `csa.uefs.br`, rate-limit e cache). Por padrão essas ferramentas ficam **desligadas** — a base remota é a fonte primária.

A decisão central está registrada em `docs/adr/002-base-conhecimento-branch-data.md` (que substitui a ADR-001): **não há RAG** (embeddings + banco vetorial). O projeto usa recuperação determinística — consulta direta aos conceitos curados e, quando ligado, ao portal — porque as consultas do domínio são lexicais ("comprovante de cota racial", "lista de espera"), a auditabilidade importa mais que a flexibilidade semântica e o custo é menor.

## O agente

| | Consumer |
|---|---|
| Papel | responder ao candidato com citação |
| Config dir | `.consumer/` |
| Ferramentas | `kb_list`, `kb_read` (+ `web_csa_fetch`/`web_csa_search` com `CHAT_CSA_PORTAL_TOOLS=1`) |
| Escrita | nenhuma: não tem credencial de admin nem alcança `write()`/`/kb/*` |

O conjunto de ferramentas é montado em `agent/factory.py` (`tools_for_config`): base fixa `[kb_list, kb_read]`; as ferramentas do portal entram apenas com `CHAT_CSA_PORTAL_TOOLS=1` (padrão `0`). Não existe mais agente ingester nem ferramentas de filesystem (`read`/`write`/`edit`/`bash`).

O system prompt é **configuração viva**: `agent/prompt.py` concatena `.consumer/AGENTS.md` + `skills/*/SKILL.md` a cada request, sem cache. Editar uma skill altera o comportamento do agente sem reiniciar o servidor.

## O caminho de uma pergunta

1. O servidor recebe a mensagem (OpenAI ou compat Ollama) e é **stateless por request** (`server/app.py`).
2. A pergunta passa pelo `qa_cache.py`: entradas de FAQ curada do prefixo `perguntas-frequentes/` da base remota são pontuadas por similaridade e injetadas no prompt como **referência**, não como resposta pronta (leitura via cliente `kb`, com cache TTL).
3. O system prompt é remontado com um guia de citações obrigatório (seção `Fontes:`, `[N]`, nunca citar caminho de arquivo — e sim a URL do frontmatter `resource:`/`url:`; conceito sem essas chaves é citado pelo título + caminho).
4. O agente decide usar ferramentas. Perguntas factuais tendem a `kb_list` → `kb_read` na base; com o portal ligado, complementa com `web_csa_search` → `web_csa_fetch` (allowlist `csa.uefs.br`, intervalo mínimo de 3s, concorrência 1, backoff em 429/5xx, cache em disco com TTL de 1h e extração de texto de PDF — tudo em `csa_portal.py`).
5. A resposta é higienizada sem ser bloqueada (`_format_agent_response`): rótulos artificiais como "Resposta:" saem, a nota de divergência órfã sai quando nenhuma fonte foi consultada, mas a seção `Fontes:` nunca é apagada. O princípio registrado no código é **guia > bloqueio**.
6. O rastro do agente (reasoning e passos de ferramenta) é reemitido nos campos extras `reasoning`/`tool_steps`, usados pelo widget para mostrar "Consultando base", "Acessando portal" etc.

## Cliente da base (`src/chat_csa/kb.py`)

Uma interface única — `list(prefix)`, `read(path)`, `write(files, message)` — usada em processo pelas tools, pelo `qa_cache` e pelos endpoints `/kb/*`:

- **Backend `github`** (deploy): `list` lê a árvore do branch de uma vez e filtra pelo prefixo; `read` baixa o arquivo (texto/base64, com download direto acima de 1MB); `write` aplica o lote num único commit via Git Data API (blobs + tree + commit + ref), nunca deixando lote parcial. Auth: `KB_TOKEN` para ler, `KB_WRITE_TOKEN` para escrever (fallback para `KB_TOKEN` com escopo de escrita).
- **Backend `local`** (dev/testes): as mesmas operações sobre `KB_LOCAL_PATH` (gitignored).
- **Renderizador** bytes→texto, usado por `kb_read` e pelo `qa_cache`: `.csv`/`.tsv` → tabela Markdown; `.pdf` → texto extraído (pdftotext via stdin, fallback `pypdf`); texto (UTF-8 válido) → direto; demais binários → aviso com tipo e tamanho. A conversão nunca é gravada no branch.
- **Cache TTL em memória** (padrão 60s) para `list`/`read`; `write` invalida as entradas afetadas. Sem escrita em disco no deploy.

## O caminho da curadoria

O time envia o conteúdo pelo endpoint `POST /kb/upload` (multipart em lote, auth admin): cada arquivo é convertido **dentro do request** num conceito OKF (`<pasta>/<slug>.md`) — PDF vira texto extraído por layout + páginas rasterizadas em chamadas multimodais; imagem vira uma chamada multimodal; `csv`/`tsv` viram tabela Markdown; `md`/`txt`/`json` entram direto. Formato sem conversão volta como `converted: false` e não é gravado; o original nunca é preservado. O campo opcional `sources` (`{"caminho": "URL"}`) adiciona `resource`/`url` e a seção `# Citations` ao conceito; conceitos e índices (seção e raiz) vão num único commit atômico, e a falha de um arquivo não aborta o lote. A base **reinicia do zero** neste refactor — o time reenvia o conteúdo; não há migração automática. O scraper do portal virou **manual** (`workflow_dispatch` em `scrape-csa.yml`): roda `scripts/scrape_portal.py` e publica a saída como artifact, sem commit — quem decide o que entra na base é o time.

Os conceitos curados seguem o formato **OKF** (um Markdown por conceito, com frontmatter `type`, `title`, `description`, `resource`, `tags`, `timestamp`); o agente cita a URL do frontmatter — conceito sem `resource`/`url` (upload avulso) é citado pelo título + caminho, nunca com URL inventada.

## Superfícies de interface

- **Widget React** (`frontend/`): botão flutuante com streaming, fontes e sugestões. Pode ser embutido em qualquer página via `public/embed.js` (iframe com `?embed=1` e `?consumerUrl=`).
- **API HTTP**: rotas OpenAI/Ollama + superfície admin `/kb/*`, documentadas em [api.md](./api.md).

## Limites atuais

O projeto está **em desenvolvimento** (status do `README.md`). A autenticação é de demonstração (usuários/tokens em memória), detalhada em [seguranca.md](./seguranca.md); o upload valida caminho e orçamento por arquivo, mas não valida o conteúdo da base. A base começa vazia e o time a alimenta pelo endpoint; enquanto isso, o chat responde que não encontrou a informação.

## Fontes

- `README.md` (arquitetura, motivação da base OKF)
- `docs/adr/002-base-conhecimento-branch-data.md`, `docs/adr/001-versionamento-base-conhecimento.md`
- `src/chat_csa/kb.py`, `src/chat_csa/server/kb_api.py`, `src/chat_csa/kb_upload.py`, `src/chat_csa/kb_convert.py`, `src/chat_csa/kb_okf.py`
- `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/prompt.py`
- `src/chat_csa/server/app.py`
- `src/chat_csa/qa_cache.py`, `src/chat_csa/csa_portal.py`
- `.consumer/AGENTS.md`, `.consumer/skills/csa-query/SKILL.md`
- `scripts/scrape_portal.py`, `.github/workflows/scrape-csa.yml`
