# Segurança

Este documento reúne o que o Chat CSA protege, o que deliberadamente ainda não protege e onde cada controle vive no código. Ele é escrito para operadores e desenvolvedores: antes de expor o sistema além do ambiente acadêmico, leia a seção de riscos conhecidos.

## Autenticação e sessão

A auth admin protege a superfície de escrita da base e o CRUD de usuários. `src/chat_csa/server/auth.py` mantém usuários e tokens **em memória**: há uma credencial-semente de demonstração definida no próprio módulo (o valor não é reproduzido aqui) e tokens de sessão no formato `tok-<uuid>` criados em `POST /auth/login`. As rotas `/auth/me`, `/admin/users` e `/kb/*` aceitam `Authorization: Bearer <token>` ou o token puro (`verify_token`); o CRUD de usuários exige o header e não expõe senhas (`_sanitize`). O próprio docstring do módulo registra o escopo: demonstração, não nível de produção. Senhas são comparadas em texto plano e não há hash, expiração de token nem revogação além da remoção do usuário.

O painel FastHTML `/admin` foi **removido** junto com o agente ingester (e com `server/admin.py`); sobraram as rotas JSON. Em ambiente serverless, usuários e tokens resetam junto com a instância: é uma limitação conhecida, não um bug.

## Base de conhecimento: quem pode ler e escrever

A base vive no branch órfão `data` do próprio repositório e é acessada pela API do GitHub:

- **Leitura** (`kb_list`/`kb_read`, `qa_cache`): acontece **em processo**, com `KB_TOKEN` (fine-grained, `contents:read`). O token nunca é exposto ao LLM: as tools não o recebem nem o interpolam no prompt.
- **Escrita** (`write()`): exige `KB_WRITE_TOKEN` (fine-grained, `contents:write`; fallback para `KB_TOKEN` com escopo de escrita) e **nunca é exposta ao agente** — só aos endpoints `/kb/*`, atrás da auth admin.
- **Superfície HTTP `/kb/*`**: `list`, `file` e `upload` exigem Bearer admin; sem token respondem 401. O agente não tem credencial de admin e não alcança `/kb/*`.
- **Upload**: o servidor valida os caminhos declarados e o orçamento por arquivo, e formato sem conversão não entra na base (volta como `converted: false`); o conteúdo em si não é validado. Quem tem o token admin pode gravar qualquer conteúdo na base; trate a credencial como de operador.
- **Commit atômico**: o lote inteiro entra num único commit via Git Data API; em falha, nada é publicado (sem lote parcial).
- **Sem escrita em disco no deploy**: o backend github não persiste arquivos localmente; o cache TTL (padrão 60s) vive na memória da instância.

## Transporte, CORS e superfícies expostas

`create_app` registra `CORSMiddleware` com `allow_origins=["*"]`, `allow_credentials=True` e todos os métodos/headers. Não há middleware de CSP, `TrustedHost` ou rate limiting no código. Na prática:

- a API do consumer é **pública por design** (o widget embutido não tem login);
- as rotas de chat não exigem token — qualquer origem pode chamá-las;
- o FastAPI mantém `/docs` e `/openapi.json` habilitados por padrão, e o CLI imprime o link de docs ao subir;
- `/kb/*` responde 401 sem token admin; `/admin/users` responde 401 sem token.

A combinação `allow_origins=["*"]` + `allow_credentials=True` merece decisão explícita antes de qualquer uso além do acadêmico.

## Ferramentas do agente e limites de acesso

O agente só recebe `kb_list` e `kb_read` (leitura da base remota, em processo). As ferramentas de filesystem (`read`/`write`/`edit`/`bash`) e o agente ingester **não existem mais** — o antigo `CHAT_CSA_ALLOW_ABSOLUTE` foi removido junto. As ferramentas do portal CSA (`web_csa_fetch`/`web_csa_search`) continuam no código, desligadas por padrão (`CHAT_CSA_PORTAL_TOOLS=0`).

O resultado das tools é truncado em 50KB/2000 linhas. A saída de `kb_read` é a conversão por tipo do arquivo original; binários viram apenas um aviso com tipo e tamanho (sem vazar conteúdo).

## Portal CSA: allowlist e polidez como controle

O acesso ao portal é limitado por código, não por prompt: `_assert_allowed` levanta `ValueError` para qualquer host diferente de `csa.uefs.br`; o intervalo mínimo entre requests (3s), a concorrência 1, o backoff e o cache em disco com TTL protegem o portal de abuso. Downloads de PDF vão para `.cache/csa-web/` (gitignored).

## Segredos e higiene do repositório

- `.gitignore` bloqueia `.env`/`.env*` (abre exceção só para `frontend/.env.production`), `.venv`, `.cache/`, `frontend/node_modules/`, `cards*.json|md`, `.vercel/*` (mantendo `.vercel/project.json`, cujo conteúdo é apenas id de projeto, não segredo) e `knowledge/` (base local de dev/testes, nunca versionada).
- Os segredos de LLM, de deploy e os tokens da base (`KB_TOKEN`, `KB_WRITE_TOKEN`) vivem como **secrets do GitHub** e são sincronizados para a Vercel por allowlist, sem impressão de valores (`scripts/sync-vercel-env.sh`, `.github/workflows/env-sync.yml`).
- `VITE_*` é público por construção: o `frontend/.env.production` contém apenas URLs.
- `frontend/public/embed.js` aceita `data-consumer-url` da página hospedeira — quem embute decide para qual backend o iframe aponta.

Nenhum valor de chave, token ou credencial é reproduzido nesta documentação; quando um segredo importa, o texto cita o arquivo que o define.

## Riscos conhecidos e prioridades

| Risco | Onde | Sugestão |
|---|---|---|
| Credencial-semente de demonstração definida em código | `server/auth.py` | permitir override/seed por ambiente e exigir troca no primeiro uso |
| Senhas em texto plano, tokens sem expiração, store volátil | `server/auth.py` | hash + store persistente antes de qualquer uso real |
| `CORS *` com credenciais e sem rate limit | `server/app.py` | restringir origens e adicionar limite por IP no proxy/gateway |
| Conversão do upload envia o conteúdo do arquivo ao provedor de LLM configurado | `kb_convert.py` | restringir o provedor/modelo da conversão (`KB_CONVERT_MODEL`) e tratar o conteúdo enviado como não confiável |
| Tokens da base com escopo amplo | `kb.py` / secrets | usar fine-grained tokens mínimos (`contents:read` para leitura) |
| `/docs` e `/openapi.json` públicos | `server/app.py` | desabilitar em produção ou proteger por rede |
| Validação por allowlist depende do domínio exato `csa.uefs.br` | `csa_portal.py` | manter a checagem e revisar em mudanças de portal |

## Fontes

- `src/chat_csa/server/auth.py`, `src/chat_csa/server/app.py`, `src/chat_csa/server/kb_api.py`
- `src/chat_csa/kb.py`
- `src/chat_csa/kb_upload.py`, `src/chat_csa/kb_convert.py`
- `src/chat_csa/agent/tools.py`, `src/chat_csa/agent/factory.py`
- `src/chat_csa/csa_portal.py`
- `.gitignore`, `.env.example`
- `.github/workflows/deploy.yml`, `.github/workflows/env-sync.yml`
- `scripts/sync-vercel-env.sh`
- `docs/integracao-widget.md`
- `README.md` (menção à credencial de demonstração)
