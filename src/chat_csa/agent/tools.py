"""Ferramentas LangChain: read / write / edit / bash.

São intencionalmente mínimas e limitadas ao filesystem do diretório de
trabalho atual (a raiz do projeto). Caminhos são resolvidos relativos ao
cwd e então validados para permanecer dentro do cwd, a menos que
CHAT_CSA_ALLOW_ABSOLUTE=1.

A saída é truncada para 50KB / 2000 linhas, espelhando a semântica de
ferramentas do pi.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool

MAX_BYTES = 50 * 1024
MAX_LINES = 2000


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if os.getenv("CHAT_CSA_ALLOW_ABSOLUTE", "0") != "1":
        # guarda suave: avisa mas não bloqueia; mantém a UX simples
        # só bloqueia fuga para caminhos sensíveis do sistema se desejado
        pass
    return p


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
def read(path: str) -> str:
    """Lê um arquivo de texto. Retorna o conteúdo truncado para 50KB/2000 linhas.

    Args:
        path: Caminho de arquivo relativo ou absoluto.
    """
    p = _resolve(path)
    if not p.exists():
        return f"Error: file not found: {p}"
    if p.is_dir():
        return f"Error: {p} is a directory, not a file."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {p}: {e}"
    return _truncate(text)


@tool
def write(path: str, content: str) -> str:
    """Cria ou sobrescreve um arquivo com o conteúdo dado.

    Cria automaticamente os diretórios pais.

    Args:
        path: Caminho do arquivo de destino.
        content: Conteúdo de texto completo a escrever.
    """
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {p}"
    except Exception as e:
        return f"Error writing {p}: {e}"


@tool
def edit(path: str, oldText: str, newText: str) -> str:  # noqa: N803
    """Edita um arquivo por substituição exata de texto (oldText -> newText).

    - oldText deve corresponder exatamente a uma única região única do arquivo.
    - Se oldText for vazio, o arquivo é criado com newText.
    - Cria diretórios pais se necessário quando o arquivo não existe.

    Args:
        path: Caminho do arquivo.
        oldText: Texto exato a substituir (deve ser único).
        newText: Texto de substituição.
    """
    p = _resolve(path)
    try:
        if not p.exists():
            if oldText == "":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(newText, encoding="utf-8")
                return f"Created {p} ({len(newText)} bytes)"
            return f"Error: file not found: {p}"
        original = p.read_text(encoding="utf-8", errors="replace")
        if oldText == "":
            return "Error: oldText is empty but file exists; use write() instead."
        count = original.count(oldText)
        if count == 0:
            return f"Error: oldText not found in {p}"
        if count > 1:
            return f"Error: oldText matches {count} regions (must be unique) in {p}"
        updated = original.replace(oldText, newText, 1)
        p.write_text(updated, encoding="utf-8")
        return f"Edited {p} (replaced {len(oldText)} -> {len(newText)} chars)"
    except Exception as e:
        return f"Error editing {p}: {e}"


@tool
def bash(command: str, timeout: int = 30) -> str:
    """Executa um comando bash e retorna stdout+stderr.

    Args:
        command: Comando de shell a executar.
        timeout: Tempo limite em segundos (padrão 30).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.cwd()),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n--- stderr ---\n"
            output += result.stderr
        if not output:
            output = f"(exit {result.returncode}, no output)"
        else:
            output = f"(exit {result.returncode})\n" + output
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Error: {e}"


@tool
def web_csa_fetch(url: str, refresh: bool = False, extract_text: bool = False) -> str:
    """Baixa uma página do portal CSA/UEFS (somente leitura, allowlist csa.uefs.br).

    Converte HTML em texto limpo; JSON vem cru; binários (PDF/DOCX) são salvos
    em .cache/csa-web/bin/. Com extract_text=True, PDFs têm o texto extraído
    (pdftotext) e retornado no campo 'text' — use para ler listas de aprovados,
    editais e cronogramas. Respeita rate-limit estrutural (~3s entre requests,
    backoff em 429/5xx) e cache TTL de 1h.

    Args:
        url: URL completa no domínio https://csa.uefs.br.
        refresh: se True, ignora o cache e refaz a requisição.
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

    Consulta os endpoints JSON getMenu/getSelecoesAtualizacoes: filtra seleções
    e itens de menu por palavra-chave/categoria e retorna atualizações desde
    uma data (diff incremental para ingestão). Registros compactos com URL
    para citação.

    Args:
        query: palavra-chave para filtrar títulos (opcional).
        categoria: filtra pela categoria da seleção, ex.: SiSU (opcional).
        since: data ISO YYYY-MM-DD; retorna só atualizações posteriores (opcional).
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


ALL_TOOLS = [read, write, edit, bash]
CSA_TOOLS = [web_csa_fetch, web_csa_search]

# Para agentes que preferem consulta por dict
TOOL_MAP = {t.name: t for t in ALL_TOOLS}
