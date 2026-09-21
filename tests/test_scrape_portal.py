"""Testes dos utilitários de scraping do portal (scripts/scrape_portal.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scrape_portal.py"
_spec = importlib.util.spec_from_file_location("scrape_portal", _SCRIPT)
assert _spec and _spec.loader
scrape_portal = importlib.util.module_from_spec(_spec)
sys.modules["scrape_portal"] = scrape_portal
_spec.loader.exec_module(scrape_portal)


def test_slugify_is_safe_and_stable():
    slug = scrape_portal.slugify("https://csa.uefs.br/index.php/sisu261/inicial")
    assert slug == "csa-uefs-br-index-php-sisu261-inicial"


def test_slugify_handles_query_and_unsafe_chars():
    slug = scrape_portal.slugify("https://csa.uefs.br/index.php/download/file/a?ext=docx")
    assert "?" not in slug and "=" not in slug
    assert slug.startswith("csa-uefs-br-index-php-download-file-a")


def test_dedupe_preserves_order():
    urls = ["https://a", "https://b", "https://a", "", "https://c"]
    assert scrape_portal._dedupe(urls) == ["https://a", "https://b", "https://c"]


def test_write_page_creates_frontmatter_and_is_idempotent(tmp_path):
    result = {
        "url": "https://csa.uefs.br/index.php/sisu261/inicial",
        "title": 'Página "oficial"',
        "fetched_at": "2026-08-26T09:00:00",
        "content_type": "text/html",
        "source_type": "html",
        "is_official": False,
    }

    assert scrape_portal.write_page(result, "corpo da página", tmp_path) is True
    path = tmp_path / "csa-uefs-br-index-php-sisu261-inicial.md"
    text = path.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert 'url: "https://csa.uefs.br/index.php/sisu261/inicial"' in text
    assert 'title: "Página \\"oficial\\""' in text
    assert "is_official: false" in text
    assert text.endswith("corpo da página\n")

    # Corpo inalterado -> não reescreve (evita commits vazios no CI).
    assert scrape_portal.write_page(result, "corpo da página", tmp_path) is False

    # Corpo novo -> reescreve.
    assert scrape_portal.write_page(result, "corpo atualizado", tmp_path) is True


# ---------------------------------------------------------------------------
# Robustez do scrape (T1): falha parcial não derruba, falha total é explícita.
# ---------------------------------------------------------------------------


def _resumo_vazio(urls):
    """Deixa o scrape rodar com uma lista de URLs controlada e sem rede."""
    return urls


def _patch_env(monkeypatch, urls, fetch, tmp_path):
    monkeypatch.setattr(scrape_portal, "_fixed_urls", lambda refresh=True: list(urls))
    monkeypatch.setattr(
        scrape_portal, "search_portal", lambda **kwargs: {"results": []}
    )
    monkeypatch.setattr(scrape_portal, "fetch_page", fetch)


def _transporte_falhou(url, refresh=False, extract_text=False):
    return {
        "url": url,
        "error": "ConnectTimeout: timed out",
        "error_type": "ConnectTimeout",
        "transport_error": True,
        "source_type": "html",
        "is_official": False,
    }


def _ok(url, refresh=False, extract_text=False):
    return {
        "url": url,
        "content": f"conteúdo de {url}",
        "source_type": "html",
        "is_official": False,
        "title": "t",
        "fetched_at": "2026-09-21T00:00:00",
        "content_type": "text/html",
    }


def test_falha_de_rede_nao_derruba_o_scrape(tmp_path, monkeypatch):
    """Uma URL que falha conta como erro; o resumo sempre sai."""
    urls = ["https://csa.uefs.br/a", "https://csa.uefs.br/b"]
    _patch_env(monkeypatch, urls, _transporte_falhou, tmp_path)

    resumo = scrape_portal.scrape(
        out_dir=tmp_path / "raw",
        refresh=True,
        max_consecutive_transport_errors=5,
    )

    assert resumo["pages"] == 0
    assert resumo["errors"] == 2
    assert resumo["error_types"] == {"ConnectTimeout": 2}
    assert resumo["aborted_reason"] == ""


def test_falha_parcial_preserva_as_paginas_boas(tmp_path, monkeypatch):
    """Falha em 1 URL não pode impedir as outras de entrar."""
    urls = ["https://csa.uefs.br/ok1", "https://csa.uefs.br/ruim", "https://csa.uefs.br/ok2"]

    def fetch(url, refresh=False, extract_text=False):
        return _transporte_falhou(url) if "ruim" in url else _ok(url)

    _patch_env(monkeypatch, urls, fetch, tmp_path)

    resumo = scrape_portal.scrape(
        out_dir=tmp_path / "raw",
        refresh=True,
        max_consecutive_transport_errors=5,
    )

    assert resumo["pages"] == 2
    assert resumo["written"] == 2
    assert resumo["errors"] == 1


def test_origem_inalcancavel_aborta_cedo(tmp_path, monkeypatch):
    """N falhas de transporte seguidas abortam, em vez de gastar o timeout do job."""
    urls = [f"https://csa.uefs.br/{i}" for i in range(10)]
    chamadas = []

    def fetch(url, refresh=False, extract_text=False):
        chamadas.append(url)
        return _transporte_falhou(url)

    _patch_env(monkeypatch, urls, fetch, tmp_path)

    resumo = scrape_portal.scrape(
        out_dir=tmp_path / "raw",
        refresh=True,
        max_consecutive_transport_errors=3,
    )

    assert len(chamadas) == 3, "deveria abortar após 3 falhas seguidas"
    assert "origem inalcançável" in resumo["aborted_reason"]
    assert resumo["urls"] == 10
