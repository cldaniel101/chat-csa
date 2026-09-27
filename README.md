# Base de conhecimento (branch `data`)

Este branch guarda **apenas o conteúdo** da base de conhecimento do Chat CSA
(bundle OKF). Ele é órfão de propósito: não compartilha código nem histórico
com os branches de desenvolvimento.

O servidor lê esta base em runtime pela API do GitHub (com cache TTL em
memória); o chat cita a URL da fonte, nunca o caminho do arquivo.

## Como enviar arquivos

1. **Pelo endpoint (recomendado):** `POST /kb/upload` — multipart em lote, com
   a auth admin. O servidor grava tudo em **um único commit atômico** neste
   branch; a resposta traz o sha do commit.
2. **Commit direto:** edite/adicione arquivos aqui e faça commit. Prefira um
   commit por lote, para não deixar lote parcial.

Arquivos podem ser enviados em qualquer formato (md, pdf, csv, binário…), sem
validação por enquanto.

## Estrutura

- O bundle fica na **raiz** deste branch (`KB_ROOT`).
- `perguntas-frequentes/` alimenta o cache de perguntas frequentes do chat.

## Leitura por tipo

O branch guarda o arquivo original; a conversão acontece só na leitura:

- `.csv` / `.tsv` → tabela Markdown;
- `.pdf` → texto extraído;
- texto (`.md`, `.txt`, `.json`, … ou UTF-8 válido) → texto direto;
- demais binários → aviso com tipo e tamanho.

A base começa vazia: até o primeiro upload, o chat responde que não encontrou
a informação (sem inventar).
