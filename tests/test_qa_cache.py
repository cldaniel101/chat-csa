from pathlib import Path

from chat_csa.qa_cache import (
    format_faq_reference,
    load_cache_entries,
    lookup_cached_answer,
    lookup_cached_matches,
)


def _write_faq(path: Path) -> None:
    path.write_text(
        """---
title: "FAQ de teste"
resource: "https://csa.uefs.br/index.php/sisu261/inicial"
last_verified: "2026-08-30"
---

# FAQ de teste

## FAQ-001 — Quais notas do ENEM posso usar no SiSU/UEFS 2026?

**Categoria:** inscrição
**Cache:** static

**Perguntas equivalentes:**
- Vale ENEM 2024?
- Posso usar o ENEM 2025?

**Resposta:**
No SiSU/UEFS 2026 podem ser utilizadas as notas do ENEM de 2023, 2024 ou 2025.

**Fonte:** Edital 01/2026, item 1.1.

---

## FAQ-002 — Quando sai a próxima chamada?

**Categoria:** cronograma
**Cache:** dynamic

**Perguntas equivalentes:**
- Já saiu a próxima chamada?

**Resposta:**
A data deve ser conferida na página oficial da CSA.

**Fonte:** Página oficial SiSU/UEFS 2026.
""",
        encoding="utf-8",
    )


def test_load_cache_entries_from_markdown(tmp_path):
    faq = tmp_path / "faq.md"
    _write_faq(faq)

    entries = load_cache_entries([faq])

    assert [entry.entry_id for entry in entries] == ["FAQ-001", "FAQ-002"]
    assert entries[0].cache_policy == "static"
    assert entries[0].alternatives == ("Vale ENEM 2024?", "Posso usar o ENEM 2025?")


def test_lookup_cached_matches_returns_top_relevant_entries(tmp_path, monkeypatch):
    faq = tmp_path / "faq.md"
    _write_faq(faq)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(faq))

    hits = lookup_cached_matches("Vale ENEM 2024?")

    assert [hit.entry.entry_id for hit in hits] == ["FAQ-001"]
    assert hits[0].matched_question == "Vale ENEM 2024?"


def test_lookup_cached_matches_includes_dynamic_entries(tmp_path, monkeypatch):
    # dynamic não short-circuita mais: entra como referência para conferência
    faq = tmp_path / "faq.md"
    _write_faq(faq)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(faq))

    hits = lookup_cached_matches("Já saiu a próxima chamada?")

    assert [hit.entry.entry_id for hit in hits] == ["FAQ-002"]


def test_format_faq_reference_marks_dynamic_entries(tmp_path, monkeypatch):
    faq = tmp_path / "faq.md"
    _write_faq(faq)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(faq))

    static = lookup_cached_matches("Vale ENEM 2024?")[0]
    dynamic = lookup_cached_matches("Já saiu a próxima chamada?")[0]

    static_block = format_faq_reference(static.entry)
    assert static_block.startswith("### FAQ-001")
    assert "confira nas fontes oficiais" not in static_block
    assert "Fonte:" in static_block

    dynamic_block = format_faq_reference(dynamic.entry)
    assert "confira nas fontes oficiais" in dynamic_block


def test_lookup_static_markdown_cache_hit(tmp_path, monkeypatch):
    faq = tmp_path / "faq.md"
    _write_faq(faq)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(faq))

    hit = lookup_cached_answer("vale enem 2024?")

    assert hit is not None
    assert hit.entry.entry_id == "FAQ-001"
    assert "notas do ENEM de 2023, 2024 ou 2025" in hit.to_markdown()
    assert "Fontes:" in hit.to_markdown()


def test_lookup_dynamic_markdown_cache_does_not_short_circuit(tmp_path, monkeypatch):
    faq = tmp_path / "faq.md"
    _write_faq(faq)
    monkeypatch.setenv("CHAT_CSA_QA_CACHE_PATHS", str(faq))

    hit = lookup_cached_answer("Já saiu a próxima chamada?")

    assert hit is None
