"""Ferramentas LangChain do agente consumer: kb_list e kb_read.

O agente lê a base de conhecimento remota (branch `data` do repositório) em
processo, via `chat_csa.kb` — nunca por HTTP e sem credencial de admin. As
ferramentas do portal CSA (`web_csa_*`) continuam no código, desligadas por
padrão (CHAT_CSA_PORTAL_TOOLS=0).

As descrições das ferramentas mandam citar a URL do frontmatter
(`resource:`/`url:`), nunca o caminho do arquivo.

A saída é truncada para 50KB / 2000 linhas, espelhando a semântica de
ferramentas do pi.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ..kb import KBError, get_kb, render_file

MAX_BYTES = 50 * 1024
MAX_LINES = 2000


def _truncate(text: str) -> str:
    lines = text.splitlines()
    truncated = False
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        truncated = True
    out = "\n".join(lines)
    if len(out.encode()) > MAX_BYTES:
        out = out.encode()[:MAX_BYTES].decode(errors="ignore")
        truncated = True
    if truncated:
        out += "\n\n[... truncated: 2000 lines / 50KB limit ...]"
    return out


@tool
def kb_list(prefix: str = "") -> str:
    """Lista os caminhos disponíveis na base de conhecimento do Chat CSA.

    Use SEMPRE antes de responder perguntas factuais: descubra o que existe
    na base e leia os arquivos relevantes com `kb_read`. O prefixo opcional
    filtra caminhos (ex.: "perguntas-frequentes/"). Os caminhos retornados
    são o argumento de `kb_read` — nunca os cite na resposta: cite a URL do
    frontmatter (`resource:` ou `url:`) do arquivo lido.

    Args:
        prefix: prefixo de caminho para filtrar (vazio = base inteira).
    """
    try:
        paths = get_kb().list(prefix)
    except KBError as exc:
        return f"Error: {exc}"
    if not paths:
        return "(base vazia ou nenhum caminho para o prefixo informado)"
    return "\n".join(paths)


@tool
def kb_read(path: str) -> str:
    """Lê um arquivo da base de conhecimento (texto renderizado por tipo).

    A conversão acontece só na leitura: .csv/.tsv viram tabela Markdown;
    .pdf tem o texto extraído; textos vêm direto; binários retornam um aviso.
    Cite sempre a URL do frontmatter (`resource:` ou `url:`) da fonte — nunca
    o caminho do arquivo. Se o arquivo não existir, confira os caminhos com
    `kb_list` antes de concluir que a informação não está na base.

    Args:
        path: caminho relativo do arquivo, como devolvido por kb_list.
    """
    try:
        file = get_kb().read(path)
    except KBError as exc:
        return f"Error: {exc}"
    return _truncate(render_file(file))


@tool
def web_csa_fetch(url: str, refresh: bool = False, extract_text: bool = False) -> str:
    """Baixa uma página do portal CSA/UEFS (somente leitura, allowlist csa.uefs.br).

    Use SEMPRE que a resposta exigir conteúdo do portal: páginas de seleção,
    resultados, editais, cronogramas e listas de aprovados. O texto das
    páginas HTML inclui os links em formato markdown [texto](url) — siga-os
    para descobrir URLs de PDFs e subpáginas. Com extract_text=True, PDFs têm
    o texto extraído no campo 'text' (pdftotext com fallback pypdf) ou um erro
    claro no campo 'text_error'. Se houver 'text_error', não afirme conteúdo
    interno do PDF; informe a limitação e cite a URL consultada. Nunca afirme
    que não há informação apenas porque web_csa_search não encontrou termo:
    abra páginas prováveis, siga links de PDFs e leia os PDFs relevantes com
    extract_text=True antes de declarar ausência.

    Args:
        url: URL completa no domínio https://csa.uefs.br.
        refresh: se True, ignora o cache (TTL 1h) e refaz a requisição.
        extract_text: se True e o conteúdo for PDF, extrai o texto do arquivo.
    """
    from ..csa_portal import fetch_page

    try:
        import json as _json
        return _json.dumps(fetch_page(url, refresh=refresh, extract_text=extract_text), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@tool
def web_csa_search(query: str = "", categoria: str = "", since: str = "", limit: int = 20) -> str:
    """Busca estruturada no catálogo do portal CSA/UEFS (somente leitura).

    Chame esta ANTES de web_csa_fetch para descobrir seleções, páginas e
    novidades — use sempre que a pergunta envolver dados do SISU/UEFS ou do
    portal da CSA, antes de responder de memória. Retorna registros compactos
    {source, id, title, url} prontos para citar e para alimentar o fetch.

    Args:
        query: palavra-chave para filtrar títulos (ex.: "resultado", "edital").
        categoria: filtra pela categoria da seleção, ex.: "sisu", "prosel".
        since: data ISO YYYY-MM-DD; retorna só atualizações posteriores (ingestão incremental).
        limit: máximo de registros retornados (padrão 20).
    """
    from ..csa_portal import search_portal

    try:
        import json as _json
        return _json.dumps(
            search_portal(query=query, categoria=categoria, since=since, limit=limit),
            ensure_ascii=False,
        )
    except Exception as e:
        return f"Error: {e}"


# Ferramentas do agente consumer (leitura da base remota).
ALL_TOOLS = [kb_list, kb_read]

# Ferramentas do portal CSA — opcionais, liberadas por CHAT_CSA_PORTAL_TOOLS=1.
CSA_TOOLS = [web_csa_fetch, web_csa_search]

# Para agentes que preferem consulta por dict
TOOL_MAP = {t.name: t for t in [*ALL_TOOLS, *CSA_TOOLS]}
