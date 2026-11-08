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


def test_scrape_classifica_documento_novo_inalterado_e_alterado(tmp_path, monkeypatch):
    url = "https://csa.uefs.br/index.php/sisu261/inicial"
    current_body = "conteúdo inicial"

    monkeypatch.setattr(scrape_portal, "_fixed_urls", lambda refresh=True: [url])
    monkeypatch.setattr(
        scrape_portal,
        "search_portal",
        lambda query, limit, refresh: {"results": []},
    )

    def fake_fetch(page_url, refresh, extract_text):
        return {
            "url": page_url,
            "title": "Página inicial",
            "fetched_at": "2026-11-08T10:00:00-03:00",
            "content_type": "text/html",
            "source_type": "html",
            "is_official": True,
            "content": current_body,
        }

    monkeypatch.setattr(scrape_portal, "fetch_page", fake_fetch)

    first = scrape_portal.scrape(tmp_path)
    assert first["written"] == 1
    assert first["changes"][0]["kind"] == "novo"
    assert first["changes"][0]["url"] == url

    unchanged = scrape_portal.scrape(tmp_path)
    assert unchanged["written"] == 0
    assert unchanged["changes"] == []

    current_body = "conteúdo atualizado"
    changed = scrape_portal.scrape(tmp_path)
    assert changed["written"] == 1
    assert changed["changes"][0]["kind"] == "alterado"


def test_main_grava_resumo_e_falha_quando_nenhuma_pagina_entra(tmp_path, monkeypatch):
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(
        scrape_portal,
        "scrape",
        lambda **kwargs: {"pages": 0, "written": 0, "errors": 1, "changes": []},
    )

    exit_code = scrape_portal.main(["--out-dir", str(tmp_path / "raw"), "--summary-json", str(summary_path)])

    assert exit_code == 2
    assert '"pages": 0' in summary_path.read_text(encoding="utf-8")
