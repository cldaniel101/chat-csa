"""Testes do módulo do portal CSA (csa_portal) e das tools web_csa_*.

Todos os testes são offline: usam mocks de HTTP (httpx MockTransport não é
usado diretamente porque o módulo cria o Client internamente; fazemos patch
de _request_with_backoff) e tmp_path para cache.
"""

import json

import pytest

import chat_csa.csa_portal as portal
from chat_csa.agent.tools import web_csa_fetch, web_csa_search


def _pdf_with_text(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 100 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\n".encode("ascii"))
    pdf.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def test_allowlist_blocks_foreign_url(monkeypatch):
    try:
        portal.fetch_page("https://example.com/pagina")
    except ValueError as e:
        assert "allowlist" in str(e)
    else:
        raise AssertionError("deveria ter bloqueado URL fora do allowlist")


def test_fetch_html_converts_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    html = (
        "<html><head><style>body{}</style></head><body>"
        "<nav>menu</nav><script>x()</script>"
        "<h1>Cronograma SISU</h1><p>Inscrições de janeiro.</p>"
        '<a href="/index.php/sisu261/cronograma_1cle">link</a>'
        "</body></html>"
    )

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}
        text = html

        def __init__(self):
            self._called = True

    calls = {"n": 0}

    def fake_request(client, url):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(portal, "_request_with_backoff", fake_request)
    out = json.loads(web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/x"}))
    assert "Cronograma SISU" in out["content"]
    assert "Inscrições" in out["content"]
    assert "x()" not in out["content"]
    # Segunda chamada deve vir do cache (sem nova request)
    out2 = json.loads(web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/x"}))
    assert out2.get("cached") is True
    assert calls["n"] == 1


def test_search_filters_menu(monkeypatch):
    menu_payload = {
        "submenu_itens": [
            {"texto_submenuitem": "Cronograma", "cabecalho_submenu": "SiSU", "link": "sisu261/cronograma_1cle"},
            {"texto_submenuitem": "Edital", "cabecalho_submenu": "ProSel", "link": "prosel151/edital"},
        ]
    }
    selecoes_payload = {
        "selecoes_categorias": [{"ID": "1", "NOME": "SiSU"}],
        "selecoes": [
            {"ID": "10", "NOME": "SiSU/UEFS 2026", "LINK": "sisu261/inicial", "CATEGORIA_ID": "1",
             "ATUALIZADO_EM": "2026-02-01 10:00"},
            {"ID": "11", "NOME": "ProSel 2015", "LINK": "prosel151/inicial", "CATEGORIA_ID": "2"},
        ],
        "atualizacoes": [
            {"ID": "1", "DATA": "2026-02-01", "TITULO": "Resultado final"},
            {"ID": "2", "DATA": "2025-01-01", "TITULO": "Antigo"},
        ],
    }

    def fake_get_json(url, refresh=False):
        return menu_payload if "getMenu" in url else selecoes_payload

    monkeypatch.setattr(portal, "_get_json", fake_get_json)

    out = json.loads(web_csa_search.invoke({"query": "cronograma"}))
    assert any("Cronograma" in r["title"] for r in out["results"])
    assert not any("ProSel 2015" == r["title"] for r in out["results"])

    out_cat = json.loads(web_csa_search.invoke({"categoria": "sisu"}))
    titles = [r["title"] for r in out_cat["results"]]
    assert "SiSU/UEFS 2026" in titles

    out_since = json.loads(web_csa_search.invoke({"since": "2026-01-01"}))
    upd = [r for r in out_since["results"] if r["source"] == "atualizacoes"]
    assert len(upd) == 1 and upd[0]["title"] == "Resultado final"


def test_search_fails_loud_on_schema_change(monkeypatch):
    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        text = "<html>not json</html>"

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(portal, "CACHE_DIR", None.__class__ and __import__("pathlib").Path("/nonexistent-cache"))
    result = web_csa_search.invoke({})
    data = json.loads(result)
    errors = [r for r in data["results"] if "error" in r]
    assert errors, "mudança de schema deve falhar com erro explícito"


def test_tools_for_config(monkeypatch, tmp_path):
    from chat_csa.agent.factory import tools_for_config
    from chat_csa.agent.tools import ALL_TOOLS

    monkeypatch.delenv("CHAT_CSA_EXTRA_TOOLS", raising=False)
    ing = tools_for_config(tmp_path / ".ingester")
    con = tools_for_config(tmp_path / ".consumer")
    assert [t.name for t in ing] == ["read", "write", "edit", "bash", "web_csa_fetch", "web_csa_search"]
    # consumer é somente leitura: read + tools CSA
    assert sorted(t.name for t in con) == ["read", "web_csa_fetch", "web_csa_search"]

    monkeypatch.setenv("CHAT_CSA_EXTRA_TOOLS", "none")
    assert [t.name for t in tools_for_config(tmp_path / ".ingester")] == [t.name for t in ALL_TOOLS]


def test_consumer_is_readonly_with_csa_tools(monkeypatch, tmp_path):
    from chat_csa.agent.factory import tools_for_config

    monkeypatch.delenv("CHAT_CSA_EXTRA_TOOLS", raising=False)
    names = [t.name for t in tools_for_config(tmp_path / ".consumer")]
    assert "web_csa_fetch" in names and "web_csa_search" in names and "read" in names
    assert not {"bash", "write", "edit"} & set(names)


def test_fetch_pdf_extracts_text_with_python_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    pdf = _pdf_with_text("Texto extraivel CSA UEFS")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = pdf
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())

    def fail_pdftotext(_pdf_path):
        raise RuntimeError("pdftotext não encontrado")

    monkeypatch.setattr(portal, "_extract_pdf_text_with_pdftotext", fail_pdftotext)

    out = json.loads(
        web_csa_fetch.invoke(
            {
                "url": "https://csa.uefs.br/index.php/download/file/sisu261/resultado",
                "extract_text": True,
            }
        )
    )

    assert out["content_type"] == "application/pdf"
    assert out["size_bytes"] == len(pdf)
    assert out["path"].endswith("resultado.pdf")
    assert out["fetched_at"]
    assert "Texto extraivel CSA UEFS" in out["text"]
    assert "text_error" not in out


def test_pdf_extraction_reports_clear_error(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"%PDF-1.4 broken")

    with pytest.raises(RuntimeError) as excinfo:
        portal._extract_pdf_text(fake)

    assert "Falha ao extrair texto do PDF" in str(excinfo.value)


def test_html_links_preserved_as_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    html = (
        '<html><body><h1>Resultados</h1>'
        '<a href="/index.php/download/file/sisu261/sisu261_resultado">Resultado Final</a>'
        "</body></html>"
    )

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}
        text = html

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    out = json.loads(web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/sisu261/x"}))
    assert "[Resultado Final](https://csa.uefs.br/index.php/download/file/sisu261/sisu261_resultado)" in out["content"]


# ---------------------------------------------------------------------------
# Testes dos novos campos de metadados (source_type, is_official,
# pdf_extraction_status, pages_extracted)
# ---------------------------------------------------------------------------


def test_html_result_has_source_type_and_is_official(tmp_path, monkeypatch):
    """Resultado HTML deve ter source_type='html' e is_official inferido pela URL."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}
        text = "<html><body><h1>Edital SISU</h1></body></html>"

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())

    # URL com /edital → is_official=True
    out_edital = json.loads(
        web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/sisu261/edital"})
    )
    assert out_edital["source_type"] == "html"
    assert out_edital["is_official"] is True

    # URL sem segmento oficial → is_official=False
    out_info = json.loads(
        web_csa_fetch.invoke({"url": "https://csa.uefs.br/index.php/sisu261/inicial", "refresh": True})
    )
    assert out_info["source_type"] == "html"
    assert out_info["is_official"] is False


def test_pdf_result_has_source_type_pdf(tmp_path, monkeypatch):
    """Resultado de PDF deve ter source_type='pdf'."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    pdf = _pdf_with_text("Conteúdo do edital oficial")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = pdf
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(portal, "_extract_pdf_text_with_pdftotext", lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")))

    out = json.loads(
        web_csa_fetch.invoke(
            {"url": "https://csa.uefs.br/index.php/download/file/sisu261/edital_sisu261", "extract_text": True}
        )
    )
    assert out["source_type"] == "pdf"
    assert out["is_official"] is True  # URL contém /edital


def test_pdf_extraction_status_completed(tmp_path, monkeypatch):
    """PDF com texto substantivo (≥50 chars) deve ter pdf_extraction_status='completed'."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    texto_longo = "A" * 60  # garante ≥50 chars
    pdf = _pdf_with_text(texto_longo)

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = pdf
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(portal, "_extract_pdf_text_with_pdftotext", lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")))

    out = json.loads(
        web_csa_fetch.invoke(
            {"url": "https://csa.uefs.br/index.php/download/file/sisu261/resultado_completo", "extract_text": True}
        )
    )
    assert out["pdf_extraction_status"] == "completed"
    assert texto_longo in out["text"]
    assert "text_error" not in out


def test_pdf_extraction_status_partial(tmp_path, monkeypatch):
    """PDF com texto muito curto (<50 chars) deve ter pdf_extraction_status='partial'."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")
    texto_curto = "OK"  # <50 chars
    pdf = _pdf_with_text(texto_curto)

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = pdf
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(portal, "_extract_pdf_text_with_pdftotext", lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")))

    out = json.loads(
        web_csa_fetch.invoke(
            {"url": "https://csa.uefs.br/index.php/download/file/sisu261/doc_parcial", "extract_text": True}
        )
    )
    assert out["pdf_extraction_status"] == "partial"
    assert "text_error" not in out


def test_pdf_extraction_status_failed(tmp_path, monkeypatch):
    """PDF com ambos os extratores falhando deve ter pdf_extraction_status='failed' e text_error."""
    monkeypatch.setattr(portal, "CACHE_DIR", tmp_path / "cache")

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/pdf"}
        content = b"%PDF-1.4 broken content"
        text = ""

    monkeypatch.setattr(portal, "_request_with_backoff", lambda c, u: FakeResp())
    monkeypatch.setattr(portal, "_extract_pdf_text_with_pdftotext", lambda p: (_ for _ in ()).throw(RuntimeError("sem pdftotext")))
    monkeypatch.setattr(portal, "_extract_pdf_text_with_pypdf", lambda p: (_ for _ in ()).throw(RuntimeError("pypdf falhou")))

    out = json.loads(
        web_csa_fetch.invoke(
            {"url": "https://csa.uefs.br/index.php/download/file/sisu261/doc_quebrado", "extract_text": True}
        )
    )
    assert out["pdf_extraction_status"] == "failed"
    assert "text_error" in out
    assert "text" not in out


def test_is_official_url_heuristic():
    """_is_official_url deve retornar True para URLs com segmentos de documento oficial."""
    assert portal._is_official_url("https://csa.uefs.br/index.php/sisu261/edital") is True
    assert portal._is_official_url("https://csa.uefs.br/index.php/download/file/sisu261/edital_sisu261") is True
    assert portal._is_official_url("https://csa.uefs.br/index.php/sisu261/downloads") is True
    assert portal._is_official_url("https://csa.uefs.br/index.php/sisu261/matricula") is True
    assert portal._is_official_url("https://csa.uefs.br/index.php/sisu261/inicial") is False
    assert portal._is_official_url("https://csa.uefs.br/index.php/sisu261/listaespera") is False
