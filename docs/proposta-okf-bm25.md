# Proposta: Pipeline Não-RAG para o Chat CSA — Bundle OKF + BM25

**Status:** Proposta em rascunho — substitui o fluxo RAG de `README.md:93-126`  
**Autor:** Davi Macêdo Gomes (+ equipe Chat CSA)  
**Data:** 2026-08-21  
**Decide:** Arquitetura de recuperação e representação de conhecimento  
**Relacionado:** `README.md` (assistente SISU/UEFS, CSA/UEFS como fonte da verdade)

---

## 1. Resumo

Substituir o pipeline de **RAG (embeddings de vetores → geração via LLM)** proposto por um pipeline **determinístico e não-generativo**:

> **Fontes cruas da CSA → Bundle de Conhecimento OKF curado → Índice lexical BM25 → Recuperação determinística → Resposta extrativa + citações**

Sem embeddings, sem banco vetorial, sem alucinação de LLM. O sistema recupera **conceitos curados por humanos e versionados** via **BM25** e os apresenta verbatim (ou com um template estritamente extrativo). Um LLM pode, opcionalmente, *verbalizar*, mas **nunca inventar** — se o bundle não tem resposta, o sistema diz *"não encontrado nas fontes oficiais"* e aponta para o portal, satisfazendo `README.md:79-83` e o `⚠️ Aviso` (`README.md:218-224`).

---

## 2. Contexto e Problema

O `README.md` propõe atualmente RAG clássico (`README.md:93-126`): incorporar pergunta → busca vetorial → LLM com contexto → resposta fundamentada. Para um chatbot genérico isso é razoável. Para o **Chat CSA**, tem falhas críticas:

| Preocupação | Por que importa para o SISU/UEFS |
|---|---|
| **Alucinação = dano legal real** | `documentos para matrícula` ou `prazo de lista de espera` errados podem causar perda de vaga. `README.md:87` diz que os editais prevalecem — o RAG torna a divergência provável (o LLM parafraseia de forma criativa). |
| **Opaco e não auditável** | Embeddings são floats de 768 dimensões; não dá para explicar *por que* o chunk #342 foi recuperado. Auditores/UEFS precisam de rastreabilidade por resposta. |
| **Terminologia jurídica em português é lexical** | Consultas são literais: `"comprovante de cota racial"`, `"chamada regular"`, `"pré-matrícula"`. Embeddings semânticos adicionam ruído; a correspondência lexical vence. |
| **Vetores obsoletos e deriva** | Cada novo `comunicado` de `csa.uefs.br` exige re-embedding + re-indexação; atualizações do modelo de embedding invalidam o índice inteiro. |
| **Custo e infraestrutura** | Banco vetorial (pgvector/Qdrant) + API de embeddings (OpenAI) = custo recorrente + vendor lock-in — ruim para um projeto de extensão universitária que precisa rodar offline/barato. |
| **Dificuldade de avaliação** | O RAG confunde *qualidade de recuperação* e *qualidade de geração*; não dá para saber qual falhou. |

**A avaliação de extensão** (`README.md:188-203`) premia diagnóstico, qualidade técnica e registro de decisões — uma base de conhecimento versionada é diretamente avaliável.

---

## 3. Decisão

**Adotar: bundle OKF (Open Knowledge Format) v0.1 como fonte única da verdade + BM25 para recuperação. Sem repositório vetorial, sem LLM generativo no caminho crítico.**

### 3.1 O que é OKF? (resumo)

* Especificação Google Cloud v0.1 — `docs: okf/spec §1-4`. Um **diretório de arquivos `.md` com frontmatter YAML** (`type` é o único campo obrigatório), interligados por links markdown, com `index.md` reservado (divulgação progressiva) e `log.md` (histórico de mudanças).
* Três princípios: *minimamente opinativo, independência produtor/consumidor, formato não plataforma* — qualquer agente/humano pode `cat`; é `git clone`-ável.
* Formaliza o padrão LLM Wiki do Karpathy: **compilar o conhecimento uma vez**, mantê-lo atual — não rederivar a cada consulta (ver `references/karpathy-llm-wiki.md`).

### 3.2 O que é BM25?

Ranking lexical probabilístico clássico (Robertson & Zaragoza, 2009). Sem embeddings. Pontua documentos por frequência de termo × frequência inversa de documento, com normalização por tamanho. Implementações: `tantivy`, `lunr`, `ElasticSearch BM25`, `rank-bm25` (Python), `sqlite FTS5`. Determinístico, explicável, rápido em <10k documentos (nossa escala), excelente para português com stemming RSLP + lista de stopwords.

---

## 4. Arquitetura Proposta

### 4.1 Pipeline (substitui `README.md:103-114`)

```text
[1] Crawler (csa.uefs.br)        ─┐
[2] Normalizador (HTML→MD, limpo) ─┤
[3] Curador → bundle OKF          ─┤  ← humano + assistência de LLM, aprovado por humano
                                  ├─→ [4] Indexador BM25 ─→ [5] API de consulta ─→ [6] UI de chat
[7] Harness de avaliação (Q&A dourado) ─┘              ↑              │
                                                 └──── feedback ──┘
                                 [8] log.md / histórico git (auditável)
```

| Etapa | Componente | Tecnologia | Notas |
|---|---|---|---|
| **1. Coletar** | Crawler | Python `requests` + `BeautifulSoup` / `playwright` para JS | Allowlist alvo: `csa.uefs.br/index.php/sisu261/*`, editais PDF, comunicados. Snapshot de HTML+PDF cru em `data/raw/{date}/` (git-ignorado, endereçado por conteúdo). Respeitar `robots.txt`. |
| **2. Normalizar** | Limpador | `pandoc`, `pymupdf`, regex | HTML/PDF → Markdown limpo, remover nav/footer, extrair `título, data, URL, tipo`. |
| **3. Compilar → OKF** | Autor do bundle | Curador humano + LLM *assistente* (nunca sem supervisão) | Cada documento da CSA → 1+ conceitos OKF (ver §5). Cross-links explícitos. `git commit` por ingestão. |
| **4. Indexar** | BM25 | `sqlite FTS5` ou `tantivy` ou `rank-bm25` (Python) | Campos do índice: `title^3, tags^2, description^2, body^1`. Tokenizador português: minúsculas, stemming RSLP, `stopwords-pt`. Rebuild em <1s para <5k conceitos. |
| **5. Consultar** | API de recuperação | `FastAPI` ou rota de API do `Next.js` | `POST /api/query {q}` → ranking BM25 → top-k conceitos (k=5) → checagem de limite. Sem geração. |
| **6. Responder** | Apresentador | Template extrativo (ver §6) | Retorna trechos verbatim dos conceitos + citações. Verbalizador LLM *opcional* só reformula texto recuperado, com citação obrigatória. |
| **7. Avaliar** | Harness | `pytest` + conjunto dourado | `tests/golden-qa/*.json` vs conceitos recuperados (não vs texto livre do LLM). |
| **8. Observar** | Log & Git | `knowledge/log.md` + `git log` | Toda mudança no bundle é diffável; respostas incluem `concept_id + git sha`. |

**Invariante de determinismo:** `consulta → score BM25 → conceitos` é reproduzível dado o mesmo bundle + índice. Sem temperatura, sem nonce.

### 4.2 Fluxo de Dados (exemplo)

> **Usuário:** *"Quais documentos preciso para matrícula da lista de espera?"*

```
query: "documentos matrícula lista de espera"
  ↓ tokenizar → [document, matrícul, list, esper] (stems RSLP)
  ↓ BM25 sobre knowledge/
  → hits:
    1. /procedimentos/matricula-documentos.md  (score 18.4) ✅
    2. /procedimentos/lista-de-espera.md       (score 14.1)
    3. /editais/sisu-2026-edital-01.md         (score  9.2)
  ↓ passa no limite (top score > 8.0)
  ↓ apresentador: concatena seção # Documentos do hit #1 + cross-link para o hit #2
  → resposta: lista extraída + Citações[1][2] + "Ver edital oficial em ..."
```

Se `max_score < limite` → `"Não encontrei essa informação nas fontes oficiais da CSA/UEFS. Consulte https://csa.uefs.br/..."` — cumpre `README.md:79`.

---

## 5. Design do Bundle OKF para o Chat CSA

### 5.1 Layout de Diretórios

```
knowledge/                          # ← raiz do bundle OKF (rastreado no git)
├── index.md                        # divulgação progressiva — lista todas as categorias
├── log.md                          # histórico cronológico de ingestão
├── editais/
│   ├── index.md
│   ├── sisu-2026-edital-01-2025-11-15.md
│   └── sisu-2026-retificacao-01-2025-12-02.md
├── cronogramas/
│   ├── index.md
│   └── sisu-2026-cronograma-geral.md
├── modalidades/
│   ├── index.md
│   ├── ampla-concorrencia.md
│   ├── cota-escola-publica.md
│   ├── cota-racial.md
│   └── cota-renda.md
├── procedimentos/
│   ├── index.md
│   ├── inscricao-sisu.md
│   ├── classificacao.md
│   ├── chamadas.md
│   ├── lista-de-espera.md
│   ├── matricula-documentos.md
│   └── recursos.md
├── perguntas-frequentes/
│   ├── index.md
│   └── faq-matricula.md
└── referencias/
    ├── index.md
    └── glossario.md
```

### 5.2 Taxonomia de Tipos de Conceito (definida pelo produtor, conforme OKF §4.1)

| `type` | Finalidade | Exemplo de arquivo |
|---|---|---|
| `Edital` | Documento normativo, maior autoridade | `editais/sisu-2026-edital-01.md` |
| `Comunicado` | Aviso/retificação oficial | `editais/sisu-2026-retificacao-01.md` |
| `Cronograma` | Tabela de datas e prazos | `cronogramas/sisu-2026-cronograma-geral.md` |
| `Modalidade` | Regras de cota/ações afirmativas | `modalidades/cota-racial.md` |
| `Procedimento` | Processo passo a passo | `procedimentos/matricula-documentos.md` |
| `FAQ` | Q&A curado e sintetizado das fontes | `perguntas-frequentes/faq-matricula.md` |
| `Referencia` | Glossário, mapa do portal | `referencias/glossario.md` |

Sem registro central — os tipos são descritivos; consumidores toleram tipos desconhecidos (OKF §9).

### 5.3 Exemplo de Conceito

`knowledge/procedimentos/matricula-documentos.md`:

```markdown
---
type: Procedimento
title: Documentos para Matrícula — SISU 2026.1 UEFS
description: Lista de documentos exigidos para matrícula de convocados na chamada regular e lista de espera.
resource: https://csa.uefs.br/index.php/sisu261/documentos-matricula
tags: [matrícula, documentos, chamada-regular, lista-de-espera, sisu-2026]
timestamp: 2025-12-02T18:00:00Z
edital_ref: /editais/sisu-2026-edital-01-2025-11-15.md
vigencia: 2026-01-01/2026-04-30
---

# Contexto

Aplica-se a candidatos convocados em [chamadas](/procedimentos/chamadas.md) e
[lista de espera](/procedimentos/lista-de-espera.md) do SISU 2026.1.
Base normativa: [Edital 01/2025](/editais/sisu-2026-edital-01-2025-11-15.md) §7.2.

# Documentos obrigatórios

- Documento oficial com foto (RG, CNH)
- CPF
- Certificado de conclusão do ensino médio
- Histórico escolar
- Comprovante de residência
- Para cotistas: comprovação conforme [modalidade](/modalidades/cota-escola-publica.md)

# Observações

- Entrega presencial no campus; ver [cronograma](/cronogramas/sisu-2026-cronograma-geral.md).
- Documentação incompleta implica perda da vaga (Edital §7.4).

# Citations

[1] [CSA — Documentos para matrícula](https://csa.uefs.br/index.php/sisu261/documentos-matricula) (acesso 2025-12-02)
[2] [Edital SISU 2026.1 §7](https://csa.uefs.br/docs/edital-01-2025.pdf) (PDF)
```

Conformidade OKF essencial: `type` não vazio, YAML parseável, cross-links válidos (`/procedimentos/...`), `# Citations` com URLs externas (OKF §8).

### 5.4 Índices

`knowledge/procedimentos/index.md` (sem frontmatter — OKF §6):

```markdown
# Procedimentos

* [Inscrição no SISU](./inscricao-sisu.md) - Como se inscrever via Portal SISU/MEC
* [Classificação](./classificacao.md) - Critérios de classificação por modalidade
* [Chamadas](./chamadas.md) - Chamada regular e convocações subsequentes
* [Lista de Espera](./lista-de-espera.md) - Manifestação e convocação da lista
* [Documentos para Matrícula](./matricula-documentos.md) - Lista de documentos exigidos (§7.2 do Edital)
...
```

`knowledge/log.md`:

```markdown
# Log de Atualizações do Conhecimento

## 2025-12-02
* **Update**: Retificação 01 — atualizou [Documentos para Matrícula](/procedimentos/matricula-documentos.md) e [Edital 01](/editais/sisu-2026-edital-01-2025-11-15.md).
* **Creation**: Adicionado [Cronograma Geral](/cronogramas/sisu-2026-cronograma-geral.md) a partir do portal CSA.

## 2025-11-15
* **Initialization**: Bundle criado; ingestão inicial de 12 páginas de sisu261 + 2 editais em PDF.
```

### 5.5 Fluxo de Autoria (humano no loop)

O LLM pode *assistir* (resumir PDF → rascunhar conceito), mas **o humano aprova** cada commit. Proteção contra prompt injection no bundle (nota de segurança do Guia da Comunidade OKF). `git diff` é a revisão.

```
nova fonte (PDF/HTML) → rascunho LLM → revisão humana → git add → rebuild BM25 (CI)
```

---

## 6. Apresentação de Respostas (Não-Generativa)

### 6.1 Nível 1 — Extrativo (padrão, sempre disponível)

Sem chamada de LLM no momento da consulta. A API retorna a(s) **seção(ões) relevante(s) verbatim** + metadados:

```json
{
  "query": "documentos matrícula lista de espera",
  "answers": [{
    "concept": "/procedimentos/matricula-documentos.md",
    "title": "Documentos para Matrícula — SISU 2026.1 UEFS",
    "excerpt": "## Documentos obrigatórios\n- Documento oficial com foto...",
    "resource": "https://csa.uefs.br/index.php/sisu261/documentos-matricula",
    "score": 18.4,
    "timestamp": "2025-12-02T18:00:00Z"
  }],
  "sources": ["https://csa.uefs.br/index.php/sisu261/documentos-matricula"],
  "disclaimer": "Informação extraída das fontes oficiais da CSA/UEFS em 2025-12-02. Em caso de divergência, prevalece o edital oficial."
}
```

A UI renderiza `excerpt` como markdown + chips de citação. Totalmente auditável, zero alucinação.

### 6.2 Nível 2 — Verbalizador Restrito (opcional, não generativo)

Se um tom mais conversacional for desejado, um LLM pode **reformular apenas os trechos recuperados**, com restrições rígidas:

* System prompt: *"Você é um verbalizador. Reescreva SOMENTE o texto em <contexto>. Não adicione fatos. Cite as fontes. Se a pergunta não for respondida no contexto, responda 'Não encontrado'."*
* Entrada = apenas os top-k conceitos (sem conhecimento externo).
* A saída é validada: toda frase deve ser implicada por um conceito citado; caso contrário, fallback para o Nível 1.
* Registrado em log: `prompt + conceitos recuperados + saída + resultado do validador`.

Isso mantém o **caminho crítico determinístico** enquanto permite um fraseado amigável quando habilitado.

---

## 7. Configuração do BM25 (Concreta)

**Motor:** `SQLite FTS5` (zero dependências, arquivo único, bom o bastante para <50k docs) **ou** `Tantivy` (Rust, mais rápido) **ou** `rank-bm25` (Python, MVP mais simples). Todos os três são BM25 puro.

**Analisador:**

* Tokenizador: fronteiras de palavra Unicode
* Normalização: NFKC, minúsculas, dobra de acentos (`à→a`)
* Stopwords: `a, o, de, do, da, em, para, com, por, que, é, ...` (lista pt-BR ~200)
* Stemming: RSLP (Removedor de Sufixos da Língua Portuguesa) — ex.: `matrícula/matrículas/matrricular → matrícul`
* Pesos de campo: `title:3, tags:2.5, description:2, body:1, resource:0.5`
* Parâmetros BM25: `k1=1.2, b=0.75` (padrões, ajustáveis)

**Limiar:** Se `top_score < 8.0` ou `top_score / second_score < 1.2` com intenção ambígua → acionar "não encontrado + desambiguação" (sugerir conceitos relacionados de `index.md`).

**Exemplo de consulta multicampo:**

```sql
-- SQLite FTS5
SELECT concept_id, bm25(knowledge_fts) as score
FROM knowledge_fts
WHERE knowledge_fts MATCH 'title:matrícula OR tags:matrícula OR body:matrícula'
ORDER BY score LIMIT 5;
```

**Construção do índice:** `python scripts/build_index.py --bundle knowledge/ --out data/bm25.db` — reexecutar a cada commit de `knowledge/` (CI, <2s).

---

## 8. Trade-offs vs RAG

| Dimensão | OKF + BM25 (proposto) | RAG (status quo) | Veredito para o Chat CSA |
|---|---|---|---|
| **Correção** | Determinístico; respostas são texto curado verbatim; alucinação = 0 (Nível 1) | O LLM pode parafrasear incorretamente mesmo com boa recuperação | **OKF vence** (crítico de segurança) |
| **Explicabilidade** | O score BM25 se decompõe por termo: "correspondeu a 'matrícula' 3× no título" | A similaridade por embedding é cosseno opaco | **OKF vence** |
| **Auditabilidade** | `git blame` no conceito + score + citação por resposta | Snapshot de vetores + prompt não reproduzível | **OKF vence** (avaliação de extensão exige registro) |
| **Atualização** | Editar arquivo → `git commit` → rebuild do índice (segundos), sem re-embedding | Re-embedding do corpus inteiro a cada atualização de modelo | **OKF vence** |
| **Custo** | $0 em runtime (sem API de embedding/LLM por consulta) | $ por 1k tokens (embeddings + geração) | **OKF vence** |
| **Consultas lexicais** | Correspondência exata em termos oficiais (`retificação`, `pré-matrícula`) | Pode recuperar doc semanticamente similar, mas legalmente errado | **OKF vence** |
| **Sinonímia / erros de digitação** | Mais fraco sem embeddings (ex.: "comprovante" vs "documento") | Melhor recall semântico | **RAG vence** — mitigado: adicionar sinônimos em `tags` + expansão de consulta (`faq-matricula` com cross-links `documento≈comprovante`), pseudo-feedback BM25+RM3 opcional |
| **Perguntas abertas** | Limitado ao que os curadores escreveram | Pode sintetizar entre muitos chunks | **RAG vence** — mitigado: conceitos FAQ exaustivos e "não encontrado" explícito é *desejado* conforme `README.md:79` |
| **Esforço de autoria** | Curadoria inicial (humano revisa cada conceito) | Menor (chunk + embed automáticos) | **RAG mais fácil** — mas a curadoria *é* o valor para informação oficial; rascunhos de LLM reduzem o esforço em 80% |
| **Escala** | Excelente <100k conceitos; BM25 O(log n) | Exige operações de banco vetorial em escala | Empate na nossa escala (~200-500 conceitos esperados) |

**Líquido:** Para o domínio **factual, oficial, em português, legal** em que `README.md:46-48,79,87` exige fidelidade à fonte, OKF+BM25 domina. As duas vantagens do RAG (sinonímia, síntese) são contornáveis sem abrir mão do determinismo.

---

## 9. Plano de Implementação

Alinhado às etapas de `README.md:136-186`:

| Etapa (README) | Ação (OKF+BM25) | Entregável |
|---|---|---|
| **1. Diagnóstico** | Pesquisar 20-30 estudantes sobre as maiores dúvidas; minerar a estrutura do portal CSA (sitemap `sisu261/*`) | `docs/pesquisas/fontes.md` (allowlist de URLs), `docs/requisitos/faq-prioritárias.md` |
| **2. Coleta** | Construir `scripts/crawl_csa.py` → snapshots em `data/raw/`; extrair texto | `data/raw/{date}/csa-*.html/pdf` |
| **3a. Bundle** | Montar `knowledge/` conforme §5.1; rascunhar conceitos (LLM-assistido, aprovado por humano); rodar `okf-validate` | `knowledge/` com ≥30 conceitos, `knowledge/index.md`, `knowledge/log.md`, CI `okf-validate` passando |
| **3b. Índice** | Implementar `scripts/build_index.py` + `api/query.py` (BM25); limiares ajustados no conjunto dourado | `data/bm25.db`, `POST /api/query` |
| **3c. UI** | UI de chat mínima (Next.js ou estática) — consulta → trechos + fontes; aviso sempre visível | `app/` ou `frontend/` |
| **4. Testes** | Criar `tests/golden-qa.json` (≥50 Q&A fundamentados nos editais); medir `Recall@5, MRR, precisão de "não encontrado"` | `docs/testes/relatorio-avaliacao.md` |
| **5. Comunidade** | Piloto com estudantes; coletar perguntas não respondidas → novos conceitos | `docs/feedbacks/` + PRs do bundle |
| **6. Evolução** | Cron `weekly` de crawl + alerta de diff (nova página da CSA → PR de rascunho de conceito) | `scripts/check_updates.py` + GitHub Action |

**Escopo do MVP (2-3 semanas, 2 pessoas):** Etapas 1-3a para um edital (`sisu-2026-edital-01`) + cronograma + 10 FAQs → ~25 conceitos → BM25 → chat que responde 80% do conjunto dourado.

---

## 10. Riscos e Mitigações

| Risco | Mitigação |
|---|---|
| Gargalo de curadoria (aprovação humana lenta) | LLM rascunha 80% do corpo; humano só verifica `Citations` + cross-links; checklist no template de PR |
| Lacuna de sinônimos (usuário diz "comprovante", conceito diz "documento") | Enriquece `tags` com sinônimos; adiciona `glossario.md`; expansão de consulta via mapa de sinônimos; reweighting RM3 opcional |
| Nova publicação da CSA não percebida | `scripts/check_updates.py` faz diff do sitemap diariamente → abre PR de rascunho + notifica via `log.md` |
| Confiança excessiva no bundle | Toda resposta mostra `timestamp` + `resource` + `git sha`; banner na UI: "Verifique no edital oficial" (conforme `README.md:220`) |
| Prompt injection via bundle | O bundle nunca é escrito a partir de entrada de usuário não confiável; apenas de URLs CSA em allowlist; CI valida domínio de `resource` = `csa.uefs.br` |
| Limiar BM25 mal ajustado | Ajustar no conjunto dourado; log A/B da distribuição de `top_score`; favorecer precisão sobre recall (melhor dizer "não encontrado" do que alucinar) |

---

## 11. Alternativas Rejeitadas Consideradas

* **RAG puro com reranker:** Ainda generativo; risco de alucinação permanece; custo/complexidade injustificados para corpus de 500 docs.
* **Fine-tuning de LLM nos editais:** Caro, obsoleto na próxima retificação, não citável.
* **RAG híbrido + BM25 (BM25 → RAG):** Adiciona complexidade sem resolver a alucinação de geração; considerado apenas como verbalizador opcional futuro de Nível 2, não padrão.
* **Sem base de conhecimento (somente LLM):** Viola `README.md:46-48` (fontes oficiais).

---

## 12. Pedido de Decisão

**Proposta de aceite:** pipeline Não-RAG (bundle OKF + BM25 + apresentação extrativa) como arquitetura oficial, superando o esboço RAG de `README.md:93-126`.

Se aceita, próximas ações:

1. Montar `knowledge/` + esqueleto de `scripts/` + `api/` (PR #1)
2. Criar ADR-001: `docs/adr/001-okf-bm25-over-rag.md`
3. Atualizar no `README.md` as seções "Funcionamento proposto" e "IA e recuperação" para refletir OKF+BM25

---

## Apêndice A — Checklist de Conformidade OKF (v0.1 §9)

- [ ] Todo `knowledge/**/*.md` (exceto `index.md`/`log.md`) tem frontmatter YAML com `type` não vazio
- [ ] `tags` presentes, `timestamp` ISO 8601, `resource` = `https://csa.uefs.br/...` quando aplicável
- [ ] Cross-links usam `/...` relativo ao bundle (recomendado) e resolvem
- [ ] Cada diretório tem `index.md` (divulgação progressiva)
- [ ] `knowledge/log.md` na raiz usa cabeçalhos `## YYYY-MM-DD`
- [ ] Validador: `node validator/okf-validate.mjs knowledge/` passando (portão de CI)

## Apêndice B — Exemplo de Contrato da API

```yaml
POST /api/query
body: { "q": "quando sai o resultado da lista de espera?", "k": 5 }
response:
  query: "quando sai o resultado da lista de espera"
  hits:
    - concept: "/cronogramas/sisu-2026-cronograma-geral.md"
      score: 16.2
      excerpt: "| Evento | Data |\n| Lista de espera - resultado | 2026-02-20 |"
    - concept: "/procedimentos/lista-de-espera.md"
      score: 13.7
  answer_mode: "extractive"
  disclaimer: "Fontes oficiais CSA/UEFS — verifique o edital vigente."
```