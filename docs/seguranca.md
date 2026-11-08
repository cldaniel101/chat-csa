# Segurança

Este documento descreve os limites de acesso do Chat CSA e a configuração necessária para operar o painel administrativo.

## Separação entre público e administrativo

O frontend usa duas rotas no mesmo domínio:

- `/`: chat público, sem login;
- `/admin`: painel da base de conhecimento, com login obrigatório.

Essa separação visual não substitui a autorização do servidor. Todas as operações administrativas em `/kb/*` e `/admin/users` verificam o token Bearer no backend. Assim, conhecer a URL ou chamar a API diretamente não libera acesso ao conteúdo protegido.

## Credencial inicial e sessão

Não existe usuário ou senha padrão no código. A autenticação fica desabilitada até estas variáveis estarem configuradas no backend:

- `CHAT_CSA_ADMIN_USERNAME`;
- `CHAT_CSA_ADMIN_PASSWORD_HASH`;
- `CHAT_CSA_AUTH_SECRET`;
- `CHAT_CSA_AUTH_SESSION_TTL` (opcional, padrão de 8 horas).

Gere o hash interativamente, sem colocar a senha no histórico do shell:

```bash
uv run python scripts/hash_admin_password.py
```

O hash usa `scrypt` com salt aleatório. `CHAT_CSA_AUTH_SECRET` deve ter no mínimo 32 bytes e deve ser gerado e armazenado como segredo do ambiente. Nenhuma dessas variáveis pode usar o prefixo `VITE_`, porque variáveis Vite são públicas no bundle do navegador.

Os tokens de sessão são assinados com HMAC-SHA256, incluem expiração e só são aceitos no formato `Authorization: Bearer <token>`. Alterar um usuário invalida as sessões anteriores desse usuário. O login aplica limite de cinco falhas por cliente em uma janela de cinco minutos.

O administrador principal é recriado a partir do ambiente em cada instância e não pode ser alterado ou excluído pela API. Usuários adicionais do CRUD são voláteis; para uma instalação com múltiplos administradores persistentes, deve-se adotar um provedor de identidade ou banco compartilhado.

## Base de conhecimento

- A leitura feita pelo agente acontece em processo e usa apenas o token de leitura da base.
- A escrita exige `KB_WRITE_TOKEN` e só é exposta pelos endpoints administrativos protegidos.
- Uploads validam caminhos e limites de tamanho, e o lote é publicado em um commit atômico.
- Segredos do GitHub e do provedor de LLM nunca são enviados ao frontend ou ao prompt.
- Fontes versionadas são autorizadas pelo processo e edição identificados na conversa. O backend confere caminho, metadados, corpo e URLs: uma fonte `sisu271` que aponte para `sisu261`, por exemplo, é rejeitada antes de chegar à resposta.
- Perguntas sem resposta são registradas sem IP, conta, sessão ou histórico. E-mail, telefone, documento e links são removidos; o texto restante é criptografado antes de ser gravado no branch público `data` e só é descriptografado por uma rota administrativa autenticada.

## CORS e headers

`CHAT_CSA_CORS_ORIGINS` define uma lista de origens autorizadas separadas por vírgula. Sem configuração, somente `http://localhost:5173` e `http://127.0.0.1:5173` são aceitos. Em produção, inclua explicitamente o domínio do frontend e as páginas oficiais que incorporam o widget.

A API não habilita credenciais CORS, restringe métodos e headers e adiciona `X-Content-Type-Options`, `Referrer-Policy` e `Permissions-Policy`. Respostas de `/auth`, `/admin` e `/kb` usam `Cache-Control: no-store`.

## Segredos e higiene do repositório

- `.env`, ambientes virtuais, dependências e caches permanecem ignorados pelo Git.
- Valores reais devem existir somente no gerenciador de segredos do ambiente de execução.
- Exemplos e testes usam apenas valores fictícios.
- `VITE_*` deve conter somente configuração pública, como a URL da API.

## Riscos remanescentes

- O limite de tentativas vive em memória e deve ser complementado por rate limiting no gateway para múltiplas instâncias.
- Usuários adicionais criados pela API não persistem em ambiente serverless.
- `/docs` e `/openapi.json` continuam públicos.
- A conversão de uploads pode enviar o conteúdo ao provedor de LLM configurado.

## Arquivos relacionados

- `src/chat_csa/server/auth.py`
- `src/chat_csa/server/app.py`
- `src/chat_csa/server/kb_api.py`
- `scripts/hash_admin_password.py`
- `.env.example`
