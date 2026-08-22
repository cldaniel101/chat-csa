"""Portal CSA/UEFS: fetch e busca read-only para o agente ingester.

Implementa a proposta v2 da discussão web-csa-tools-for-ingester:

- ``fetch_page``  — GET com allowlist do domínio csa.uefs.br; HTML → texto
  limpo (stdlib, sem deps extras) ou download binário (PDF/DOCX) para disco.
- ``search_portal`` — consulta estruturada sobre os endpoints JSON
  ``/index.php/ajax/getMenu`` e ``/index.php/ajax/getSelecoesAtualizacoes``
  (filtro por palavra-chave/categoria e diff de atualizações por timestamp).

Politeness estrutural (nunca em prompt):
- intervalo mínimo entre requisições (CSA_MIN_INTERVAL_S, padrão 3s),
- concorrência 1 (trava global),
- backoff exponencial em 429/5xx com honra a Retry-After,
- cache TTL em disco (.cache/csa-web/, gitignored).
"""

from __future__ import annotations

import json
import re
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_HOST = "csa.uefs.br"
BASE_URL = "https://csa.uefs.br"
MENU_URL = f"{BASE_URL}/index.php/ajax/getMenu"
SELECOES_URL = f"{BASE_URL}/index.php/ajax/getSelecoesAtualizacoes"
DOWNLOAD_PREFIX = f"{BASE_URL}/index.php/download/file/"

MIN_INTERVAL_S = float(__import__("os").getenv("CSA_MIN_INTERVAL_S", "3"))
CACHE_DIR = Path(__import__("os").getenv("CSA_CACHE_DIR", ".cache/csa-web"))
CACHE_TTL_S = float(__import__("os").getenv("CSA_CACHE_TTL_S", "3600"))
MAX_BACKOFF_S = 60.0
USER_AGENT = "chat-csa-ingester/1.0 (projeto de extensao UEFS; leitura apenas)"

_lock = threading.Lock()
_last_request_ts = 0.0


# ---------------------------------------------------------------------------
# Politeness: intervalo mínimo + concorrência 1
# ---------------------------------------------------------------------------


def _throttle() -> None:
    """Dorme o necessário para respeitar o intervalo mínimo entre requests."""
    global _last_request_ts
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request_ts)
        if wait > 0:
            time.sleep(wait)
        _last_request_ts = time.monotonic()


def _request_with_backoff(client: httpx.Client, url: str) -> httpx.Response:
    """GET com backoff exponencial em 429/5xx (honra Retry-After)."""
    delay = 2.0
    for attempt in range(4):
        _throttle()
        resp = client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        if resp.status_code < 400:
            return resp
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable or attempt == 3:
            return resp
        retry_after = resp.headers.get("Retry-After")
        sleep_s = float(retry_after) if (retry_after or "").isdigit() else delay
        time.sleep(min(sleep_s, MAX_BACKOFF_S))
        delay *= 2
    return resp  # inalcançável; satisfaz tipos


def _assert_allowed(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host != BASE_HOST:
        raise ValueError(f"URL fora do allowlist ({BASE_HOST}): {url}")


# ---------------------------------------------------------------------------
# Cache em disco
# ---------------------------------------------------------------------------


def _cache_path(url: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-180:]
    return CACHE_DIR / (slug + ".cache")


def _cache_get(url: str) -> tuple[str, str] | None:
    p = _cache_path(url)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > CACHE_TTL_S:
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["content_type"], data["body"]


def _cache_put(url: str, content_type: str, body: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(url).write_text(
        json.dumps({"content_type": content_type, "body": body}), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# HTML → texto limpo (stdlib)
# ---------------------------------------------------------------------------

_SKIP_TAGS = {"script", "style", "noscript", "svg", "form", "iframe"}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "tr", "h1", "h2", "h3",
    "h4", "h5", "h6", "br", "table", "ul", "ol", "header", "footer", "nav",
}


class _TextExtractor(HTMLParser):
    """Extrai texto visível e links em formato markdown [texto](url).

    Links relativos são resolvidos contra a URL da página (base_url), para
    que o agente consiga descobrir URLs de PDFs e subpáginas a partir do
    texto extraído.
    """

    def __init__(self, base_url: str = "") -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._base_url = base_url
        self._pending_href: str | None = None
        self._link_text: list[str] = []

    def _abs(self, href: str) -> str:
        if href.startswith("http") or not self._base_url:
            return href
        from urllib.parse import urljoin

        return urljoin(self._base_url, href)

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self._pending_href = value
                    self._link_text = []
                    break

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "a":
            text = " ".join(t.strip() for t in self._link_text)
            if self._pending_href:
                label = text or self._pending_href
                self._chunks.append(f"[{label}]({self._abs(self._pending_href)}) ")
            elif text:
                self._chunks.append(text + " ")
            self._pending_href = None
            self._link_text = []
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self._pending_href is not None:
            self._link_text.append(stripped)
        else:
            self._chunks.append(stripped + " ")

    @property
    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [ln.strip() for ln in raw.splitlines()]
        out: list[str] = []
        for ln in lines:
            if ln or (out and out[-1]):
                out.append(ln)
        return "\n".join(out)


def html_to_text(html: str, base_url: str = "") -> str:
    ext = _TextExtractor(base_url=base_url)
    try:
        ext.feed(html)
    except Exception:
        return html  # fallback: devolve bruto se o parse falhar
    return ext.text.strip()


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extrai texto de um PDF com pdftotext (poppler-utils).

    Levanta erro claro se o poppler não estiver instalado.
    """
    import shutil
    import subprocess

    if shutil.which("pdftotext") is None:
        raise RuntimeError(
            "pdftotext não encontrado: instale poppler-utils para extração de PDF "
            "(ex.: apt install poppler-utils)"
        )
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext falhou em {pdf_path}: {result.stderr[:300]}")
    return result.stdout.strip()


def fetch_page(url: str, refresh: bool = False, extract_text: bool = False) -> dict:
    """Baixa uma URL do portal (allowlist) retornando dict com provenance.

    HTML é convertido para texto limpo; binários (PDF/DOCX...) são salvos
    em disco sob CACHE_DIR/bin/ e retornados via campo 'path'.
    """
    _assert_allowed(url)

    if not refresh:
        cached = _cache_get(url)
        if cached is not None:
            content_type, body = cached
            return _build_result(url, content_type, body, cached=True)

    with httpx.Client(timeout=30) as client:
        resp = _request_with_backoff(client, url)

    if resp.status_code != 200:
        return {"url": url, "error": f"HTTP {resp.status_code}", "fetched_at": _now_iso()}
    content_type = resp.headers.get("Content-Type", "")
    if "html" in content_type.lower() or "json" in content_type.lower():
        text = html_to_text(resp.text, base_url=url) if "html" in content_type.lower() else resp.text
        _cache_put(url, content_type, text)
        return _build_result(url, content_type, text)
    # binário: salva em disco (não cachear conteúdo na chave .cache)
    bin_dir = CACHE_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    name = urlparse(url).path.rstrip("/").split("/")[-1] or "download"
    dest = bin_dir / name
    dest.write_bytes(resp.content)
    result = {
        "url": url,
        "title": name,
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "path": str(dest),
        "size_bytes": len(resp.content),
    }
    if extract_text and ("pdf" in content_type.lower() or name.lower().endswith(".pdf")):
        # extração de texto embutida apenas para PDF (via pdftotext)
        try:
            result["text"] = _extract_pdf_text(dest)
        except Exception as e:
            result["text_error"] = str(e)
    return result


def _build_result(url: str, content_type: str, body: str, cached: bool = False) -> dict:
    first_line = body.splitlines()[0][:120] if body else ""
    truncated = False
    # JSON não é truncado (quebraria o parse); a via compacta é web_csa_search
    max_chars = 50_000 if "json" not in content_type.lower() else float("inf")
    content = body
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True
    return {
        "url": url,
        "title": first_line,
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "cached": cached,
        "truncated": truncated,
        "chars": len(content),
        "content": content,
    }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# search: consultas estruturadas sobre os endpoints JSON
# ---------------------------------------------------------------------------


def _get_json(url: str, refresh: bool = False) -> dict | list:
    if not refresh:
        cached = _cache_get(url)
        if cached is not None:
            return json.loads(cached[1])
    with httpx.Client(timeout=30) as client:
        resp = _request_with_backoff(client, url)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} em {url}")
    ctype = resp.headers.get("Content-Type", "")
    if "json" not in ctype.lower():
        raise RuntimeError(f"Schema inesperado em {url}: Content-Type={ctype!r}")
    _cache_put(url, ctype, resp.text)
    return resp.json()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def search_portal(
    query: str = "",
    categoria: str = "",
    since: str = "",
    limit: int = 20,
    refresh: bool = False,
) -> dict:
    """Busca estruturada no catálogo do portal.

    - query/categoria filtram seleções e itens de menu;
    - since (YYYY-MM-DD) retorna atualizações posteriores à data (diff incremental).
    Retorna registros compactos {id, title, url, updated_at}.
    """
    results: list[dict] = []

    # Menu completo
    try:
        menu = _get_json(MENU_URL, refresh=refresh)
        for item in menu.get("submenu_itens", []) or []:
            text = _norm(f"{item.get('texto_submenuitem', '')} {item.get('cabecalho_submenu', '')}")
            if query and query.lower() not in text:
                continue
            link = item.get("link") or item.get("LINK") or ""
            full = link if link.startswith("http") else f"{BASE_URL}/index.php/{link}"
            results.append({"source": "menu", "id": "", "title": item.get("texto_submenuitem", ""), "url": full})
    except Exception as e:
        results.append({"source": "menu", "error": str(e), "title": "", "url": MENU_URL})

    # Catálogo de seleções + atualizações
    try:
        sel = _get_json(SELECOES_URL, refresh=refresh)
        cats = {}
        for c in sel.get("selecoes_categorias", []) or []:
            cid = c.get("ID") or c.get("id")
            cats[cid] = c.get("NOME") or c.get("nome") or ""

        for key in ("selecoes", "selecao"):
            for s in sel.get(key, []) or []:
                nome = s.get("NOME") or s.get("nome") or ""
                cat_id = s.get("CATEGORIA_ID") or s.get("categoria_id") or s.get("ID_CATEGORIA")
                cat_name = cats.get(cat_id, "") if cat_id is not None else (s.get("CATEGORIA") or s.get("categoria") or "")
                if query and query.lower() not in _norm(nome):
                    continue
                if categoria and categoria.lower() not in _norm(cat_name):
                    continue
                link = s.get("LINK") or s.get("link") or ""
                full = link if link.startswith("http") else f"{BASE_URL}/index.php/{link}"
                results.append({
                    "source": "selecoes",
                    "id": s.get("ID") or s.get("id") or "",
                    "title": nome,
                    "url": full,
                    "categoria": cat_name,
                    "updated_at": s.get("ATUALIZADO_EM") or s.get("atualizado_em") or "",
                })

        updates = sel.get("atualizacoes") or sel.get("updates") or []
        for u in updates:
            when = str(u.get("DATA") or u.get("data") or u.get("updated_at") or "")
            if since and when[:10] < since:
                continue
            results.append({
                "source": "atualizacoes",
                "id": u.get("ID") or u.get("id") or "",
                "title": u.get("TITULO") or u.get("titulo") or u.get("TEXTO") or u.get("texto") or "",
                "url": BASE_URL,
                "updated_at": when,
            })
    except Exception as e:
        results.append({"source": "selecoes", "error": str(e), "title": "", "url": SELECOES_URL})

    return {"count": len(results), "results": results[: max(1, int(limit))], "queried_at": _now_iso()}
