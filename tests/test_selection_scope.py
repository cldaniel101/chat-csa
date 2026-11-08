"""Filtro de processo/edição aplicado antes de responder."""

from __future__ import annotations

import json

from chat_csa.agent.tools import kb_list, kb_read, web_csa_fetch, web_csa_search
from chat_csa.qa_cache import lookup_cached_matches
from chat_csa.selection_scope import (
    SelectionScope,
    assess_source,
    infer_selection_scope,
    reset_selection_scope,
    response_source_mismatches,
    set_selection_scope,
    source_rejection_reason,
)


def _invoke_in_scope(scope: SelectionScope, tool, arguments: dict) -> str:
    token = set_selection_scope(scope)
    try:
        return tool.invoke(arguments)
    finally:
        reset_selection_scope(token)


def _document(year: int, *, link_year: int | None = None) -> str:
    link_year = year if link_year is None else link_year
    return f'''---
title: "Documentação SiSU {year}"
description: "Documento do SiSU/UEFS {year}."
resource: "https://csa.uefs.br/index.php/sisu{year % 100:02d}1/documentacao"
tags: [sisu-{year}, matricula]
---

# Documentação do SiSU {year}

Consulte os modelos em https://csa.uefs.br/index.php/sisu{link_year % 100:02d}1/downloads.
'''


def test_infer_scope_separates_sisu_editions_and_preserves_follow_up():
    scope_2026 = infer_selection_scope(["Quais documentos do SiSU 2026?"])
    scope_2027 = infer_selection_scope(["Quais documentos do SiSU 2027?"])
    follow_up = infer_selection_scope(["Quero saber do SiSU 2027", "E os documentos?"])

    assert (scope_2026.process, scope_2026.year, scope_2026.slug) == ("sisu", 2026, "sisu261")
    assert (scope_2027.process, scope_2027.year, scope_2027.slug) == ("sisu", 2027, "sisu271")
    assert (follow_up.process, follow_up.year, follow_up.slug) == ("sisu", 2027, "sisu271")


def test_new_process_does_not_inherit_year_from_previous_process():
    scope = infer_selection_scope(
        ["Quero saber do ProSel 2015", "Na verdade, quais documentos do SiSU?"],
    )

    assert scope.process == "sisu"
    assert scope.year is None
    assert scope.needs_clarification is True


def test_latest_explicit_process_and_year_replace_previous_scope():
    scope = infer_selection_scope(
        ["Quero saber do SiSU 2027", "Agora consulte o ProSel 2015"],
    )

    assert (scope.process, scope.year) == ("prosel", 2015)


def test_enem_year_is_not_mistaken_for_selection_edition():
    scope = infer_selection_scope(["Posso usar o ENEM 2024?"])

    assert scope.year is None
    assert scope.needs_clarification is True


def test_assessment_rejects_2027_document_with_2026_reference():
    text = _document(2027, link_year=2026)
    source = assess_source("manuais/sisu271_documentacao_cotista.md", text)
    scope = infer_selection_scope(["Documentação do SiSU 2027"])

    assert (source.process, source.year, source.edition) == ("sisu", 2027, 1)
    assert any("sisu261" in url for url in source.mismatched_references)
    assert "outra edição" in (source_rejection_reason(scope, source) or "")


def test_kb_list_and_read_are_filtered_by_requested_edition(kb_local):
    manuals = kb_local / "manuais"
    manuals.mkdir()
    (manuals / "sisu261_documentacao.md").write_text(_document(2026), encoding="utf-8")
    (manuals / "sisu271_documentacao.md").write_text(_document(2027), encoding="utf-8")
    (manuals / "sisu271_links_antigos.md").write_text(
        _document(2027, link_year=2026),
        encoding="utf-8",
    )
    scope = infer_selection_scope(["Quais documentos do SiSU 2027?"])

    listing = _invoke_in_scope(scope, kb_list, {"prefix": "manuais"})
    clean = _invoke_in_scope(scope, kb_read, {"path": "manuais/sisu271_documentacao.md"})
    wrong_year = _invoke_in_scope(scope, kb_read, {"path": "manuais/sisu261_documentacao.md"})
    stale_link = _invoke_in_scope(scope, kb_read, {"path": "manuais/sisu271_links_antigos.md"})

    assert "sisu271_documentacao.md" in listing
    assert "sisu271_links_antigos.md" in listing
    assert "sisu261_documentacao.md" not in listing
    assert "Documentação do SiSU 2027" in clean
    assert wrong_year.startswith("Error: fonte rejeitada")
    assert "SISU 2026" in wrong_year
    assert stale_link.startswith("Error: fonte rejeitada")
    assert "sisu261" in stale_link


def test_ambiguous_selection_question_cannot_open_versioned_sources(kb_local):
    manuals = kb_local / "manuais"
    manuals.mkdir()
    (manuals / "sisu261_documentacao.md").write_text(_document(2026), encoding="utf-8")
    scope = infer_selection_scope(["Quais documentos preciso para a matrícula?"])

    listing = _invoke_in_scope(scope, kb_list, {"prefix": "manuais"})
    content = _invoke_in_scope(scope, kb_read, {"path": "manuais/sisu261_documentacao.md"})

    assert "informe o processo seletivo e o ano" in listing
    assert "informe o processo seletivo e o ano" in content


def test_faq_2027_pointing_to_2026_is_removed_before_prompt(kb_local):
    faq_dir = kb_local / "perguntas-frequentes"
    faq_dir.mkdir()
    (faq_dir / "faq-2027.md").write_text(
        '''---
title: "FAQ SiSU 2027"
resource: "https://csa.uefs.br/index.php/sisu261/inicial"
---

## FAQ-271 — Quais documentos preciso no SiSU 2027?

**Cache:** static

**Resposta:**
Documentos da edição 2027 com referência antiga.
''',
        encoding="utf-8",
    )
    scope = infer_selection_scope(["Quais documentos preciso no SiSU 2027?"])

    hits = lookup_cached_matches("Quais documentos preciso no SiSU 2027?", scope=scope)

    assert hits == []


def test_final_response_guard_detects_cross_edition_url():
    scope = infer_selection_scope(["Quais documentos do SiSU 2027?"])
    response = (
        "Use estes documentos.\n\nFontes:\n"
        "[1] Documentação — https://csa.uefs.br/index.php/sisu261/downloads"
    )

    assert response_source_mismatches(response, scope) == (
        "https://csa.uefs.br/index.php/sisu261/downloads",
    )


def test_portal_fetch_rejects_wrong_edition_before_network(monkeypatch):
    import chat_csa.csa_portal as portal

    called = False

    def fake_fetch(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(portal, "fetch_page", fake_fetch)
    scope = infer_selection_scope(["Edital do SiSU 2027"])

    output = _invoke_in_scope(
        scope,
        web_csa_fetch,
        {"url": "https://csa.uefs.br/index.php/sisu261/edital"},
    )

    assert output.startswith("Error: URL rejeitada")
    assert called is False


def test_portal_fetch_rejects_2027_page_with_embedded_2026_link(monkeypatch):
    import chat_csa.csa_portal as portal

    monkeypatch.setattr(
        portal,
        "fetch_page",
        lambda *args, **kwargs: {
            "url": "https://csa.uefs.br/index.php/sisu271/inicial",
            "content": "Baixe em https://csa.uefs.br/index.php/sisu261/downloads",
        },
    )
    scope = infer_selection_scope(["Documentos do SiSU 2027"])

    output = _invoke_in_scope(
        scope,
        web_csa_fetch,
        {"url": "https://csa.uefs.br/index.php/sisu271/inicial"},
    )

    assert output.startswith("Error: conteúdo rejeitado")
    assert "sisu261" in output


def test_portal_search_separates_sisu_and_other_processes(monkeypatch):
    import chat_csa.csa_portal as portal

    monkeypatch.setattr(
        portal,
        "search_portal",
        lambda **kwargs: {
            "count": 3,
            "results": [
                {"title": "SiSU 2026", "url": "https://csa.uefs.br/index.php/sisu261/inicial"},
                {"title": "SiSU 2027", "url": "https://csa.uefs.br/index.php/sisu271/inicial"},
                {"title": "ProSel 2015", "url": "https://csa.uefs.br/index.php/prosel151/inicial"},
            ],
        },
    )

    sisu_output = json.loads(
        _invoke_in_scope(
            infer_selection_scope(["SiSU 2027"]),
            web_csa_search,
            {"query": "edital"},
        )
    )
    prosel_output = json.loads(
        _invoke_in_scope(
            infer_selection_scope(["ProSel 2015"]),
            web_csa_search,
            {"query": "edital"},
        )
    )

    assert [item["title"] for item in sisu_output["results"]] == ["SiSU 2027"]
    assert [item["title"] for item in prosel_output["results"]] == ["ProSel 2015"]
