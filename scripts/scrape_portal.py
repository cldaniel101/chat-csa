#!/usr/bin/env python3
"""Scrape do portal CSA/UEFS para `knowledge/raw/`.

Faz o trabalho pesado do workflow `.github/workflows/scrape-csa.yml`:

1. Monta uma lista fixa de URLs a partir do slug vigente do SiSU
   (`_latest_selection_slug("sisu")`) — nada de hardcode de `sisu261`.
2. Descobre URLs adicionais via `search_portal`.
3. Deduplica e busca cada página com `fetch_page(..., extract_text=True)`.
4. Grava o conteúdo em `knowledge/raw/{slug}.md` com frontmatter de
   proveniência (url, title, fetched_at, content_type, source_type,
   is_official).

O conteúdo bruto é a fonte para o agente consumidor citar a **URL** da
página, nunca o caminho do arquivo Markdown.

Uso:
    python scripts/scrape_portal.py [--out-dir knowledge/raw]
                                    [--limit 50] [--no-refresh] [--dry-run]
                                    [--summary-json scrape-summary.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

# Importa o pacote instalado; se rodar sem `uv sync`, cai para `src/`.
try:
    from chat_csa.csa_portal import (
        _latest_selection_slug,
        fetch_page,
        search_portal,
    )
except ImportError:  # pragma: no cover - conveniência para execução local
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from chat_csa.csa_portal import (
        _latest_selection_slug,
        fetch_page,
        search_portal,
    )

# Slug de fallback caso o menu do portal esteja indisponível no momento.
FALLBACK_SLUG = "sisu261"

# Páginas fixas do ciclo vigente, relativas ao slug da seleção.
FIXED_PATHS = ("inicial", "downloads", "edital")

# Limite de caracteres do slug de arquivo (evita nomes gigantes).
MAX_SLUG_LEN = 120


def _fixed_urls(refresh: bool = True) -> list[str]:
    """Monta a lista fixa de URLs a partir do slug vigente do SiSU."""
    slug = _latest_selection_slug("sisu", refresh=refresh) or FALLBACK_SLUG
    return [f"https://csa.uefs.br/index.php/{slug}/{path}" for path in FIXED_PATHS]


def _dedupe(urls: list[str]) -> list[str]:
    """Remove URLs repetidas preservando a ordem de descoberta."""
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def slugify(url: str) -> str:
    """Converte uma URL em um nome de arquivo seguro (ex.: `csa-uefs-br-index-php-sisu261-inicial`)."""
    parsed = urlparse(url)
    raw = unquote(f"{parsed.netloc}{parsed.path}")
    if parsed.query:
        raw = f"{raw}-{parsed.query}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
    return (slug or "index")[:MAX_SLUG_LEN]


def _yaml_str(value: str) -> str:
    """Serializa uma string como escalar YAML entre aspas (JSON é YAML válido)."""
    return json.dumps(str(value), ensure_ascii=False)


def _frontmatter(result: dict, slug: str, body: str) -> str:
    """Monta o bloco de frontmatter com a proveniência da página."""
    url = result.get("url", "")
    title = result.get("title") or slug
    fetched_at = result.get("fetched_at", "")
    content_type = result.get("content_type", "")
    source_type = result.get("source_type", "")
    is_official = "true" if result.get("is_official") else "false"
    return (
        "---\n"
        f"url: {_yaml_str(url)}\n"
        f"title: {_yaml_str(title)}\n"
        f"fetched_at: {_yaml_str(fetched_at)}\n"
        f"content_type: {_yaml_str(content_type)}\n"
        f"source_type: {_yaml_str(source_type)}\n"
        f"is_official: {is_official}\n"
        "---\n\n"
    )


def _existing_body(path: Path) -> str | None:
    """Devolve o corpo atual do arquivo (sem frontmatter) ou `None`."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + len("\n---\n") :].strip()
    return text.strip()


def write_page(result: dict, body: str, out_dir: Path) -> bool:
    """Grava `knowledge/raw/{slug}.md`. Retorna True se o arquivo mudou.

    Se o corpo não mudou, preserva o arquivo anterior — assim o `fetched_at`
    só avança quando há conteúdo novo e o workflow não gera commits vazios.
    """
    slug = slugify(result.get("url", ""))
    path = out_dir / f"{slug}.md"
    body = body.strip()
    if _existing_body(path) == body:
        return False
    path.write_text(_frontmatter(result, slug, body) + body + "\n", encoding="utf-8")
    return True


def scrape(
    out_dir: Path,
    limit: int = 50,
    refresh: bool = True,
    dry_run: bool = False,
) -> dict:
    """Executa o scrape completo e devolve um resumo numérico."""
    out_dir.mkdir(parents=True, exist_ok=True)

    discovery_errors = 0
    try:
        fixed = _fixed_urls(refresh=refresh)
    except httpx.HTTPError as exc:
        fixed = [f"https://csa.uefs.br/index.php/{FALLBACK_SLUG}/{path}" for path in FIXED_PATHS]
        discovery_errors += 1
        print(f"[aviso] falha de rede ao descobrir o ciclo vigente ({type(exc).__name__}); usando fallback")
    print(f"[scrape] URLs fixas: {len(fixed)}")

    try:
        search = search_portal(query="", limit=limit, refresh=refresh)
        discovered = [str(item["url"]) for item in search.get("results", []) if item.get("url")]
    except httpx.HTTPError as exc:
        discovered = []
        discovery_errors += 1
        print(f"[aviso] falha de rede na busca do portal ({type(exc).__name__}); seguindo com URLs fixas")
    print(f"[scrape] URLs descobertas na busca: {len(discovered)}")

    urls = _dedupe(fixed + discovered)
    print(f"[scrape] URLs únicas a processar: {len(urls)}")

    pages = 0
    written = 0
    errors = discovery_errors
    changes: list[dict[str, str]] = []

    for url in urls:
        try:
            result = fetch_page(url, refresh=refresh, extract_text=True)
        except httpx.HTTPError as exc:
            print(f"[aviso] falha de rede ao buscar {url}: {type(exc).__name__}")
            errors += 1
            continue

        if result.get("error"):
            if "não encontrada" in str(result["error"]):
                # Rota lógica que não existe neste ciclo do portal: pular sem
                # tratar como falha (ex.: /edital quando só há o PDF em downloads).
                print(f"[pular] página inexistente no portal: {url}")
            else:
                print(f"[aviso] falha ao buscar {url}: {result['error']}")
                errors += 1
            continue

        # PDF extraído -> campo `text`; HTML/JSON -> campo `content`.
        body = result.get("text") or result.get("content") or ""
        if not body.strip():
            print(f"[aviso] sem conteúdo textual em {url} — pulando")
            errors += 1
            continue

        pages += 1
        if dry_run:
            print(f"[dry-run] {url} -> {slugify(url)}.md ({len(body)} chars)")
            continue

        slug = slugify(url)
        output_path = out_dir / f"{slug}.md"
        existed = output_path.exists()
        if write_page(result, body, out_dir):
            written += 1
            changes.append(
                {
                    "kind": "alterado" if existed else "novo",
                    "path": output_path.as_posix(),
                    "url": str(result.get("url", url)),
                    "title": str(result.get("title") or slug),
                }
            )
            print(f"[ok] {slug}.md ({len(body)} chars)")
        else:
            print(f"[=] {slug}.md inalterado")

    summary = {
        "pages": pages,
        "written": written,
        "errors": errors,
        "changes": changes,
    }
    print(f"\nResumo: {pages} páginas raspadas, {written} arquivos escritos, {errors} erros")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape do portal CSA/UEFS para knowledge/raw/.")
    parser.add_argument(
        "--out-dir",
        default="knowledge/raw",
        type=Path,
        help="Diretório de saída (padrão: knowledge/raw).",
    )
    parser.add_argument(
        "--limit",
        default=50,
        type=int,
        help="Máximo de URLs descobertas na busca (padrão: 50).",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Usa o cache local em vez de forçar download.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não grava arquivos; apenas lista o que seria feito.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Grava o resumo da execução em JSON (usado pelo workflow de alerta).",
    )
    args = parser.parse_args(argv)

    summary = scrape(
        out_dir=args.out_dir,
        limit=args.limit,
        refresh=not args.no_refresh,
        dry_run=args.dry_run,
    )
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    # Falha fechada: sem nenhuma página não há como afirmar que o portal está
    # inalterado, então o workflow não deve avançar nem enviar aviso enganoso.
    return 0 if summary["pages"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
