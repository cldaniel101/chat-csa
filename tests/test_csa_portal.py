"""Testes do módulo do portal CSA (csa_portal) e das tools web_csa_*.

Todos os testes são offline: usam mocks de HTTP (httpx MockTransport não é
usado diretamente porque o módulo cria o Client internamente; fazemos patch
de _request_with_backoff) e tmp_path para cache.
"""

import json

import chat_csa.csa_portal as portal
from chat_csa.agent.tools import web_csa_fetch, web_csa_search


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


def test_pdf_extraction(tmp_path, monkeypatch):
    # PDF mínimo válido gerado na mão não é viável; usamos pdftotext num PDF real
    # de fixture: cria um PDF de 1 página com texto via pdftotext é impossível,
    # então testamos apenas o caminho de erro para arquivo inválido.
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"%PDF-1.4 broken")
    try:
        portal._extract_pdf_text(fake)
    except RuntimeError as e:
        assert "pdftotext falhou" in str(e)
    else:
        raise AssertionError("deveria falhar em PDF inválido")
