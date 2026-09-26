# Arquitetura

Este documento explica como o Chat CSA funciona por dentro: quem coleta e organiza a informação, quem responde ao candidato, por onde uma pergunta passa e por que o projeto trocou RAG por um bundle de conhecimento curado. A primeira seção é um resumo legível sem conhecimento técnico; as seguintes descem ao detalhe.

## Resumo para não-devs

O Chat CSA tem dois "funcionários" de IA com papéis separados. O **ingester** navega no portal oficial da CSA/UEFS, baixa editais, cronogramas e páginas, e organiza tudo num acervo em Markdown revisável — a pasta `knowledge/`. O **consumer** é quem conversa com o público: ele consulta esse acervo e o próprio portal antes de responder, sempre dizendo de qual página tirou cada informação. Quando não encontra a resposta, o sistema foi projetado para dizer que não encontrou — em vez de inventar. O site do chat é um botão flutuante que pode ser embutido na página da CSA; o painel interno, usado pela equipe para alimentar a base, é uma tela separada no servidor.

## Visão em camadas

```text
Fontes oficiais da CSA/UEFS (portal csa.uefs.br, PDFs)
        ↓  ingester: web_csa_search / web_csa_fetch (allowlist, rate-limit, cache)
Bundle OKF curado (knowledge/) + páginas raspadas (knowledge/raw/)
        ↓  consumer: read do bundle, FAQ curada injetada, fetch do portal quando falta
Resposta extrativa com citações (Fontes: com URL e horário de acesso)
        ↓
Usuário (widget React embutível / API OpenAI-compatible / painel /admin do ingester)
```

A decisão central está registrada no `README.md` e no `docs/adr/001-versionamento-base-conhecimento.md`: **não há RAG** (embeddings + banco vetorial). O projeto usa recuperação determinística — consulta direta a conceitos curados e ao portal — porque as consultas do domínio são lexicais ("comprovante de cota racial", "lista de espera"), a auditabilidade importa mais que a flexibilidade semântica e o custo é menor.

## Os dois agentes

| | Ingester | Consumer |
|---|---|---|
| Papel | coletar, normalizar e curar fontes | responder ao candidato com citação |
| Config dir | `.ingester/` | `.consumer/` |
| Ferramentas | `read`, `write`, `edit`, `bash` + `web_csa_fetch`, `web_csa_search` | `read` + `web_csa_fetch`, `web_csa_search` |
| Escrita | pode alterar o bundle (`knowledge/`) | nunca escreve nem executa comandos |

A separação é imposta por código em `agent/factory.py` (`tools_for_config`): o nome do config dir decide o conjunto de ferramentas, então o consumer não recebe `bash`, `write` nem `edit`. Os dois processos compartilham o mesmo pacote e a mesma API; o que muda é o config dir, a porta e o conjunto de tools.

Em ambos, o system prompt é **configuração viva**: `agent/prompt.py` concatena `AGENTS.md` + `skills/*/SKILL.md` a cada request, sem cache. Editar uma skill altera o comportamento do agente sem reiniciar o servidor.

## O caminho de uma pergunta

1. O servidor recebe a mensagem (OpenAI ou compat Ollama) e é **stateless por request** (`server/app.py`).
2. A pergunta passa pelo `qa_cache.py`: entradas de FAQ curada (`docs/faq/` e `knowledge/perguntas-frequentes/`) são pontuadas por similaridade e injetadas no prompt como **referência**, não como resposta pronta.
3. O system prompt é remontado com um guia de citações obrigatório (seção `Fontes:`, `[N]`, nunca citar caminho de arquivo).
4. O agente decide usar ferramentas. Perguntas factuais tendem a `read` no bundle e, se faltar, `web_csa_search` → `web_csa_fetch`. O fetch é limitado ao domínio `csa.uefs.br`, com intervalo mínimo de 3s entre requests, concorrência 1, backoff em 429/5xx, cache em disco com TTL de 1h e extração de texto de PDF (`pdftotext`, fallback `pypdf`) — tudo em `csa_portal.py`.
5. A resposta é higienizada sem ser bloqueada (`_format_agent_response`): rótulos artificiais como "Resposta:" saem, a nota de divergência órfã sai quando nenhuma fonte foi consultada, mas a seção `Fontes:` nunca é apagada. O princípio registrado no código é **guia > bloqueio**.
6. O rastro do agente (reasoning e passos de ferramenta) é reemitido nos campos extras `reasoning`/`tool_steps`, usados pelo widget para mostrar "Acessando portal", "Acessando PDF" etc.

## O caminho da curadoria

O workflow `scrape-csa.yml` roda a cada 12 horas, executa `scripts/scrape_portal.py` e versiona o que mudou em `knowledge/raw/` (um Markdown por página, com frontmatter `url`, `title`, `fetched_at`, `content_type`, `source_type`, `is_official`). O consumer cita a URL do frontmatter — nunca o caminho do arquivo. A curadoria de conceitos no bundle segue as skills `csa-ingest`, `okf` e `ingester-incremental-ingest` e registra cada lote em `knowledge/log.md`; o bundle em si é versionado no Git por decisão do ADR-001.

## Superfícies de interface

- **Widget React** (`frontend/`): exclusivo do consumer; botão flutuante com streaming, fontes e sugestões. Pode ser embutido em qualquer página via `public/embed.js` (iframe com `?embed=1` e `?consumerUrl=`).
- **Painel `/admin`** (`server/admin.py`): exclusivo do ingester; FastHTML servido pelo próprio backend com login por cookie e chat SSE. O consumer responde 404 nessa rota. A decisão de separar os dois frontends está registrada no código ("decisão da discussão ingester-fasthtml-admin").
- **API HTTP**: as mesmas rotas OpenAI/Ollama para ambos, documentadas em [api.md](./api.md).

## Limites atuais

O projeto está **em desenvolvimento** (status do `README.md`). A autenticação é de demonstração (usuários/tokens em memória), detalhada em [seguranca.md](./seguranca.md); o bundle cobre o SiSU/UEFS 2026 e depende de curadoria humana para se manter atual.

## Fontes

- `README.md` (arquitetura, motivação do bundle OKF)
- `docs/adr/001-versionamento-base-conhecimento.md`
- `src/chat_csa/agent/factory.py`, `src/chat_csa/agent/prompt.py`
- `src/chat_csa/server/app.py`
- `src/chat_csa/qa_cache.py`, `src/chat_csa/csa_portal.py`
- `knowledge/index.md`
- `.ingester/AGENTS.md`, `.consumer/AGENTS.md`
- `scripts/scrape_portal.py`, `.github/workflows/scrape-csa.yml`
- `.consumer/skills/csa-query/SKILL.md`
