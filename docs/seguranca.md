# Segurança

Este documento reúne o que o Chat CSA protege, o que deliberadamente ainda não protege e onde cada controle vive no código. Ele é escrito para operadores e desenvolvedores: antes de expor o sistema além do ambiente acadêmico, leia a seção de riscos conhecidos.

## Autenticação e sessão

O ingester é o único agente com autenticação. `src/chat_csa/server/auth.py` mantém usuários e tokens **em memória**: há uma credencial-semente de demonstração definida no próprio módulo (o valor não é reproduzido aqui) e tokens de sessão no formato `tok-<uuid>` criados em `POST /auth/login`. As rotas `/auth/me` e `/admin/users` aceitam `Authorization: Bearer <token>` ou o token puro (`verify_token`); o CRUD de usuários exige o header e não expõe senhas (`_sanitize`). O próprio docstring do módulo registra o escopo: "apenas para demonstração — não é nível de produção". Senhas são comparadas em texto plano e não há hash, expiração de token nem revogação além da remoção do usuário.

O painel `/admin` (`server/admin.py`) usa o mesmo store, mas troca o Bearer por cookie `csa_admin_token` (`HttpOnly`, `SameSite=Lax`, `path=/admin`; `Secure` quando `ADMIN_COOKIE_SECURE=1`). A chave de sessão do FastHTML pode ser fixada por `CHAT_CSA_ADMIN_SECRET_KEY` (e gravada em `CHAT_CSA_ADMIN_KEY_FILE`, default `/tmp/.sesskey`) — sem ela, cada cold start invalida sessões. Em ambiente serverless, usuários e tokens resetam junto com a instância: é uma limitação conhecida, não um bug.

## Transporte, CORS e superfícies expostas

`create_app` registra `CORSMiddleware` com `allow_origins=["*"]`, `allow_credentials=True` e todos os métodos/headers. Não há middleware de CSP, `TrustedHost` ou rate limiting no código. Na prática:

- a API do consumer é **pública por design** (o widget embutido não tem login);
- as rotas de chat não exigem token — qualquer origem pode chamá-las;
- o FastAPI mantém `/docs` e `/openapi.json` habilitados por padrão, e o CLI imprime o link de docs ao subir;
- `/admin` responde 404 no processo do consumer; `/admin/users` responde 401 sem token.

A combinação `allow_origins=["*"]` + `allow_credentials=True` merece decisão explícita antes de qualquer uso além do acadêmico.

## Ferramentas do agente e limites de acesso

As ferramentas de arquivo (`agent/tools.py`) resolvem caminhos relativos ao diretório de trabalho e o resultado é truncado em 50KB/2000 linhas. Existe a variável `CHAT_CSA_ALLOW_ABSOLUTE` (default `0`), mas hoje ela é um **guarda suave documentado como tal**: o `_resolve` não bloqueia caminhos absolutos quando o valor é `0` — o comentário do código diz explicitamente "avisa mas não bloqueia". A ferramenta `bash` executa comandos de shell sem sandbox adicional. O controle real de privilégio é o conjunto de ferramentas por agente: o consumer nunca recebe `bash`, `write` nem `edit` (`tools_for_config`).

## Portal CSA: allowlist e polidez como controle

O acesso ao portal é limitado por código, não por prompt: `_assert_allowed` levanta `ValueError` para qualquer host diferente de `csa.uefs.br`; o intervalo mínimo entre requests (3s), a concorrência 1, o backoff e o cache em disco com TTL protegem o portal de abuso. Downloads de PDF vão para `.cache/csa-web/` (gitignored). As páginas raspadas em `knowledge/raw/` são conteúdo público do portal, versionadas de propósito.

## Segredos e higiene do repositório

- `.gitignore` bloqueia `.env`/`.env*` (abre exceção só para `frontend/.env.production`), `.venv`, `.cache/`, `frontend/node_modules/`, `.sesskey`, `cards*.json|md` e `.vercel/*` (mantendo `.vercel/project.json`, cujo conteúdo é apenas id de projeto, não segredo).
- Os segredos de LLM e de deploy vivem como **secrets do GitHub** e são sincronizados para a Vercel por allowlist, sem impressão de valores (`scripts/sync-vercel-env.sh`, `.github/workflows/env-sync.yml`).
- `VITE_*` é público por construção: o `frontend/.env.production` contém apenas URLs.
- `frontend/public/embed.js` aceita `data-consumer-url` da página hospedeira — quem embute decide para qual backend o iframe aponta.

Nenhum valor de chave, token ou credencial é reproduzido nesta documentação; quando um segredo importa, o texto cita o arquivo que o define.

## Riscos conhecidos e prioridades

| Risco | Onde | Sugestão |
|---|---|---|
| Credencial-semente de demonstração definida em código | `server/auth.py` | permitir override/seed por ambiente e exigir troca no primeiro uso |
| Senhas em texto plano, tokens sem expiração, store volátil | `server/auth.py` | hash + store persistente antes de qualquer uso real |
| `CORS *` com credenciais e sem rate limit | `server/app.py` | restringir origens e adicionar limite por IP no proxy/gateway |
| `bash` sem sandbox e caminhos absolutos não bloqueados | `agent/tools.py` | endurecer `_resolve`/desabilitar `bash` onde não for necessário |
| `/docs` e `/openapi.json` públicos | `server/app.py` | desabilitar em produção ou proteger por rede |
| Validação por allowlist depende do domínio exato `csa.uefs.br` | `csa_portal.py` | manter a checagem e revisar em mudanças de portal |

## Fontes

- `src/chat_csa/server/auth.py`, `src/chat_csa/server/app.py`, `src/chat_csa/server/admin.py`
- `src/chat_csa/agent/tools.py`, `src/chat_csa/agent/factory.py`
- `src/chat_csa/csa_portal.py`
- `.gitignore`, `.env.example`
- `.github/workflows/deploy.yml`, `.github/workflows/env-sync.yml`
- `scripts/sync-vercel-env.sh`
- `docs/integracao-widget.md`
- `README.md` (menção à credencial de demonstração)
