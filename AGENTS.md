# AGENTS.md — Chat CSA

## 🗣️ Idioma

Neste projeto:

- **Código** pode ser escrito em inglês.
- **Comentários e documentação** devem ser escritos em português (pt-BR).
- **Conversa** (respostas, issues, PRs e discussões): use o idioma que o usuário preferir.

## 🌿 Convenções de Git

- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Mensagens de commit em português, no imperativo (ex.: `feat: adiciona busca no portal`).
- Um commit por mudança lógica; commits pequenos e atômicos.
- `main` = estável (apenas versões). Trabalho do dia a dia acontece em `development`.
- Não commitar segredos, `.env`, `.venv/`, `frontend/node_modules/` ou caches.

## 🔐 Segredos e notificações por e-mail

- O `.env` da raiz já contém as variáveis de backend `CHAT_CSA_EMAIL_API_URL`, `CHAT_CSA_EMAIL_API_TOKEN` e `CHAT_CSA_UPDATE_NOTIFICATION_TO`.
- Essas variáveis configuram a API de e-mail usada para avisar quando um documento precisa de revisão após uma atualização manual aprovada.
- Acessar os valores somente no backend por variáveis de ambiente. Nunca copiar, exibir ou registrar os valores em código, documentação, logs, respostas ou arquivos versionados.
- Nunca expor essas configurações ao frontend nem criar equivalentes com o prefixo `VITE_`.
- Em exemplos e testes, usar apenas valores fictícios ou variáveis vazias.
