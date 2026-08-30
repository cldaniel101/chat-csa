"""Portal CSA/UEFS: fetch e busca read-only para o agente ingester.

Implementa a proposta v2 da discussão web-csa-tools-for-ingester:

- ``fetch_page``  — GET com allowlist do domínio csa.uefs.br; HTML → texto
  limpo ou download binário (PDF/DOCX) para disco. PDFs podem ter texto
  extraído com ``pdftotext`` e fallback Python via ``pypdf``.
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
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import httpx

BASE_HOST = "csa.uefs.br"
BASE_URL = "https://csa.uefs.br"
MENU_URL = f"{BASE_URL}/index.php/ajax/getMenu"
SELECOES_URL = f"{BASE_URL}/index.php/ajax/getSelecoesAtualizacoes"
DOWNLOAD_PREFIX = f"{BASE_URL}/index.php/download/file/"
LEGACY_SELECTION_PREFIXES = {"sisu"}
PROCESS_QUERY_HINTS = {
    "classificacao",
    "concorrencia",
    "convocacao",
    "corte",
    "curso",
    "documento",
    "edital",
    "enem",
    "engenharia",
    "espera",
    "lista",
    "matricula",
    "maxima",
    "minima",
    "modalidade",
    "nota",
    "notas",
    "resultado",
    "sisu",
    "vagas",
}

MIN_INTERVAL_S = float(__import__("os").getenv("CSA_MIN_INTERVAL_S", "3"))
CACHE_DIR = Path(__import__("os").getenv("CSA_CACHE_DIR", ".cache/csa-web"))
CACHE_TTL_S = float(__import__("os").getenv("CSA_CACHE_TTL_S", "3600"))
MAX_BACKOFF_S = 60.0
USER_AGENT = "chat-csa-ingester/1.0 (projeto de extensao UEFS; leitura apenas)"

# Segmentos de URL que indicam documento oficial (edital, resultado final, matrícula)
_OFFICIAL_URL_SEGMENTS = (
    "/edital",
    "/downloads",
    "/resultado_final",
    "/matricula",
    "/regulamento",
    "/convocacao",
)

_lock = threading.Lock()
_last_request_ts = 0.0
_PORTAL_NOT_FOUND_MARKERS = (
    "erro - a p",
    "foi encontrada",
    "requisitou",
)


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


def _extract_pdf_text_with_pdftotext(pdf_path: Path) -> str:
    """Extrai texto de um PDF com pdftotext (poppler-utils)."""
    import shutil
    import subprocess

    if shutil.which("pdftotext") is None:
        raise RuntimeError(
            "pdftotext não encontrado; instale poppler-utils para usar o extrator do sistema"
        )
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"pdftotext falhou em {pdf_path}: {detail[:300]}")
    return result.stdout.strip()


def _extract_pdf_text_with_pypdf(pdf_path: Path) -> str:
    """Extrai texto de um PDF usando a dependência Python pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf não encontrado; execute `uv sync` ou instale a dependência Python") from exc

    try:
        reader = PdfReader(str(pdf_path))
        chunks: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text.strip())
        return "\n\n".join(chunks).strip()
    except Exception as exc:
        raise RuntimeError(f"pypdf falhou em {pdf_path}: {exc}") from exc


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extrai texto de um PDF com Poppler e fallback Python.

    A ordem prioriza ``pdftotext`` porque costuma preservar melhor layout de
    editais/listas. Quando o binário não existe ou falha, ``pypdf`` mantém a
    extração funcional em desenvolvimento e testes automatizados.
    """
    errors: list[str] = []
    for name, extractor in (
        ("pdftotext", _extract_pdf_text_with_pdftotext),
        ("pypdf", _extract_pdf_text_with_pypdf),
    ):
        try:
            text = extractor(pdf_path)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if text:
            return text
        errors.append(f"{name}: nenhum texto extraível encontrado")

    raise RuntimeError("Falha ao extrair texto do PDF. Tentativas: " + "; ".join(errors))


def _count_pdf_pages_with_text(pdf_path: Path) -> int | None:
    """Retorna a quantidade de páginas com texto extraível via pypdf.

    Retorna None se pypdf não estiver disponível ou a leitura falhar.
    Usado apenas para preencher o campo ``pages_extracted`` nos metadados.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return sum(1 for p in reader.pages if (p.extract_text() or "").strip())
    except Exception:
        return None


def _is_official_url(url: str) -> bool:
    """Infere se a URL aponta para um documento oficial (edital, resultado, matrícula).

    A heurística é baseada em segmentos de caminho comuns no portal csa.uefs.br.
    Não substitui julgamento humano, mas permite que o agente diferencie
    fontes primárias (edital, convocação) de páginas informativas genéricas.
    """
    lower = url.lower()
    return any(seg in lower for seg in _OFFICIAL_URL_SEGMENTS)


def _is_portal_not_found_text(text: str) -> bool:
    """Detecta a página de erro interna do portal, mesmo quando o HTTP vem 200."""
    lower = text.lower()
    return all(marker in lower for marker in _PORTAL_NOT_FOUND_MARKERS)


def _selection_slug_from_link(link: str, prefix: str) -> str:
    path = urlparse(link).path if link.startswith("http") else link
    parts = [part for part in path.strip("/").split("/") if part and part != "index.php"]
    if not parts:
        return ""
    slug = parts[0].lower()
    return slug if re.fullmatch(rf"{re.escape(prefix)}\d+[a-z0-9]*", slug) else ""


def _latest_selection_slug(prefix: str, refresh: bool = False) -> str:
    """Encontra o slug vigente de uma seleção no menu oficial, ex.: sisu -> sisu261."""
    try:
        menu = _get_json(MENU_URL, refresh=refresh)
    except Exception:
        return ""

    candidates: list[str] = []
    for item in menu.get("submenu_itens", []) or []:
        link = item.get("link") or item.get("LINK") or ""
        slug = _selection_slug_from_link(str(link), prefix)
        if slug:
            candidates.append(slug)

    return candidates[0] if candidates else ""


def _resolve_legacy_selection_url(url: str, refresh: bool = False) -> str:
    """Resolve rotas genéricas quebradas do portal, como /index.php/sisu/inicial."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 3 or parts[0] != "index.php":
        return url

    selection_prefix = parts[1].lower()
    if selection_prefix not in LEGACY_SELECTION_PREFIXES:
        return url

    latest_slug = _latest_selection_slug(selection_prefix, refresh=refresh)
    if not latest_slug:
        return url

    resolved_path = "/" + "/".join([parts[0], latest_slug, *parts[2:]])
    return urlunparse(parsed._replace(path=resolved_path))


def _suggest_portal_alternatives(url: str, refresh: bool = False) -> list[str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0] != "index.php":
        return [BASE_URL]

    selection_prefix = parts[1].lower()
    if re.fullmatch(r"sisu\d+[a-z0-9]*", selection_prefix):
        latest_slug = selection_prefix
    elif selection_prefix in LEGACY_SELECTION_PREFIXES:
        latest_slug = _latest_selection_slug(selection_prefix, refresh=refresh)
    else:
        latest_slug = ""

    if not latest_slug:
        return [BASE_URL]

    return [
        f"{BASE_URL}/index.php/{latest_slug}/inicial",
        f"{BASE_URL}/index.php/{latest_slug}/downloads",
        f"{BASE_URL}/index.php/{latest_slug}/edital",
    ]


def _portal_not_found_result(
    url: str,
    *,
    content_type: str,
    content: str,
    requested_url: str | None = None,
    cached: bool = False,
    refresh: bool = False,
) -> dict:
    result = {
        "url": url,
        "error": "Página não encontrada no portal CSA/UEFS",
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "source_type": "html",
        "is_official": False,
        "cached": cached,
        "truncated": False,
        "chars": len(content),
        "content": content[:2000],
        "suggested_urls": _suggest_portal_alternatives(requested_url or url, refresh=refresh),
    }
    if requested_url and requested_url != url:
        result["resolved_from_url"] = requested_url
    return result


def _mark_resolved(result: dict, requested_url: str) -> dict:
    if requested_url != result.get("url"):
        result["resolved_from_url"] = requested_url
    return result


def _filename_from_response(url: str, headers: httpx.Headers | dict, is_pdf: bool) -> str:
    """Escolhe um nome estável para salvar o download em cache/bin."""
    content_disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", content_disposition, flags=re.IGNORECASE)
    if match:
        name = unquote(match.group(1).strip().strip('"'))
    else:
        name = urlparse(url).path.rstrip("/").split("/")[-1] or "download"
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip() or "download"
    if is_pdf and not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name


def _is_pdf_response(content_type: str, name: str, body: bytes) -> bool:
    """Detecta PDF por Content-Type, extensão ou assinatura do arquivo."""
    lower_type = content_type.lower()
    return "pdf" in lower_type or name.lower().endswith(".pdf") or body.startswith(b"%PDF")


def fetch_page(url: str, refresh: bool = False, extract_text: bool = False) -> dict:
    """Baixa uma URL do portal (allowlist) retornando dict com provenance.

    HTML é convertido para texto limpo; binários (PDF/DOCX...) são salvos
    em disco sob CACHE_DIR/bin/ e retornados via campo 'path'.

    Campos retornados (todos os tipos):
    - url, fetched_at, content_type, is_official  (sempre presentes)
    - source_type: "pdf" | "html" | "json" | "binary"
    - cached, truncated, chars, content  (HTML/JSON)
    - path, size_bytes, title            (binários)
    - text                               (PDF com extração concluída)
    - text_error                         (PDF com falha de extração)
    - pdf_extraction_status              ("completed" | "partial" | "failed") — apenas PDF com extract_text=True
    - pages_extracted                    (int) — apenas PDF com pypdf bem-sucedido
    """
    _assert_allowed(url)
    requested_url = url
    url = _resolve_legacy_selection_url(url, refresh=refresh)
    _assert_allowed(url)

    if not refresh:
        cached = _cache_get(url)
        if cached is not None:
            content_type, body = cached
            if "html" in content_type.lower() and _is_portal_not_found_text(body):
                return _portal_not_found_result(
                    url,
                    content_type=content_type,
                    content=body,
                    requested_url=requested_url,
                    cached=True,
                    refresh=refresh,
                )
            return _mark_resolved(_build_result(url, content_type, body, cached=True), requested_url)

    with httpx.Client(timeout=30) as client:
        resp = _request_with_backoff(client, url)

    if resp.status_code != 200:
        result = {
            "url": url,
            "error": f"HTTP {resp.status_code}",
            "fetched_at": _now_iso(),
            "is_official": _is_official_url(url),
            "source_type": "html",
        }
        return _mark_resolved(result, requested_url)

    content_type = resp.headers.get("Content-Type", "")
    if "html" in content_type.lower() or "json" in content_type.lower():
        text = html_to_text(resp.text, base_url=url) if "html" in content_type.lower() else resp.text
        if "html" in content_type.lower() and _is_portal_not_found_text(text):
            return _portal_not_found_result(
                url,
                content_type=content_type,
                content=text,
                requested_url=requested_url,
                refresh=refresh,
            )
        _cache_put(url, content_type, text)
        return _mark_resolved(_build_result(url, content_type, text), requested_url)
    # binário: salva em disco (não cachear conteúdo na chave .cache)
    bin_dir = CACHE_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    raw_name = urlparse(url).path.rstrip("/").split("/")[-1] or "download"
    is_pdf = _is_pdf_response(content_type, raw_name, resp.content)
    name = _filename_from_response(url, resp.headers, is_pdf=is_pdf)
    dest = bin_dir / name
    dest.write_bytes(resp.content)
    result: dict = {
        "url": url,
        "title": name,
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "source_type": "pdf" if is_pdf else "binary",
        "is_official": _is_official_url(url),
        "path": str(dest),
        "size_bytes": len(resp.content),
    }
    if extract_text and is_pdf:
        # Extração de texto embutida apenas para PDF.
        try:
            extracted = _extract_pdf_text(dest)
            result["text"] = extracted
            # Status: completo quando há conteúdo substantivo (≥50 chars)
            if len(extracted.strip()) >= 50:  # noqa: PLR2004
                result["pdf_extraction_status"] = "completed"
                pages = _count_pdf_pages_with_text(dest)
                if pages is not None:
                    result["pages_extracted"] = pages
            else:
                result["pdf_extraction_status"] = "partial"
        except Exception as e:
            result["text_error"] = str(e)
            result["pdf_extraction_status"] = "failed"
    elif extract_text:
        result["text_error"] = "extração de texto disponível apenas para PDF"
        result["pdf_extraction_status"] = "failed"
    return _mark_resolved(result, requested_url)


def _build_result(url: str, content_type: str, body: str, cached: bool = False) -> dict:
    first_line = body.splitlines()[0][:120] if body else ""
    truncated = False
    # JSON não é truncado (quebraria o parse); a via compacta é web_csa_search
    max_chars = 50_000 if "json" not in content_type.lower() else float("inf")
    content = body
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True
    # Determina source_type pelo Content-Type
    lower_ct = content_type.lower()
    if "html" in lower_ct:
        source_type = "html"
    elif "json" in lower_ct:
        source_type = "json"
    else:
        source_type = "binary"
    return {
        "url": url,
        "title": first_line,
        "fetched_at": _now_iso(),
        "content_type": content_type,
        "source_type": source_type,
        "is_official": _is_official_url(url),
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


def _strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(s)).strip().lower()


def _query_matches(query: str, text: str) -> bool:
    normalized_query = _norm(query)
    normalized_text = _norm(text)
    if not normalized_query:
        return True
    if normalized_query in normalized_text:
        return True

    terms = [
        term
        for term in re.split(r"[^a-z0-9]+", normalized_query)
        if len(term) >= 3
    ]
    return bool(terms) and any(term in normalized_text for term in terms)


def _looks_like_process_query(query: str, categoria: str = "") -> bool:
    terms = set(re.split(r"[^a-z0-9]+", _norm(f"{query} {categoria}")))
    return bool(terms & PROCESS_QUERY_HINTS)


def _selection_short_title(slug: str) -> str:
    match = re.fullmatch(r"sisu(\d{2})(\d)", slug)
    if not match:
        return slug.upper()
    year = int(match.group(1)) + 2000
    edition = match.group(2)
    return f"SiSU/UEFS {year}.{edition}"


def _latest_sisu_fallback_results(refresh: bool = False) -> list[dict]:
    slug = _latest_selection_slug("sisu", refresh=refresh)
    if not slug:
        return []

    title = _selection_short_title(slug)
    return [
        {
            "source": "fallback",
            "id": slug,
            "title": f"{title} — página inicial",
            "url": f"{BASE_URL}/index.php/{slug}/inicial",
        },
        {
            "source": "fallback",
            "id": slug,
            "title": f"{title} — downloads, editais e anexos",
            "url": f"{BASE_URL}/index.php/{slug}/downloads",
        },
        {
            "source": "fallback",
            "id": slug,
            "title": f"{title} — edital",
            "url": f"{BASE_URL}/index.php/{slug}/edital",
        },
    ]


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
            if not _query_matches(query, text):
                continue
            link = item.get("link") or item.get("LINK") or ""
            if not link:
                continue
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
                if not _query_matches(query, nome):
                    continue
                if categoria and not _query_matches(categoria, cat_name):
                    continue
                link = s.get("LINK") or s.get("link") or ""
                if not link:
                    continue
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

    if not results and _looks_like_process_query(query, categoria):
        results.extend(_latest_sisu_fallback_results(refresh=refresh))

    return {"count": len(results), "results": results[: max(1, int(limit))], "queried_at": _now_iso()}
