# Snippet de integração do Chat CSA

Este snippet permite incorporar o chat em páginas externas do site da CSA por meio de um único bloco HTML. O script cria um iframe isolado para evitar conflitos de CSS ou JavaScript com a página hospedeira.

## Uso em produção

Substitua `https://chat-csa-web.vercel.app` pela URL pública do frontend do Chat CSA:

```html
<script
  src="https://chat-csa-web.vercel.app/embed.js"
  data-chat-url="https://chat-csa-web.vercel.app"
  data-consumer-url="https://chat-csa-api.vercel.app"
  defer
></script>
```

## Uso local

Com o consumer rodando em `http://localhost:8002` e o frontend em `http://localhost:5173`:

```html
<script
  src="http://localhost:5173/embed.js"
  data-chat-url="http://localhost:5173"
  data-consumer-url="http://localhost:8002"
  defer
></script>
```

## Opções

- `data-chat-url`: URL onde o frontend do chat está hospedado.
- `data-consumer-url`: URL da API consumer usada pelo chat.
- `data-position`: lado do botão flutuante. Use `right` ou `left`. Padrão: `right`.
- `data-bottom`: distância da parte inferior da tela. Padrão: `16px`.
- `data-side`: distância lateral. Padrão: `16px`.
- `data-z-index`: camada visual do iframe. Padrão: `2147483000`.
- `data-title`: título acessível do iframe. Padrão: `Assistente CSA`.
