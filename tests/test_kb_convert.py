"""Testes da conversão de uploads (`chat_csa.kb_convert`)."""

from __future__ import annotations

import pymupdf
import pytest

from chat_csa.kb_convert import (
    ConversionError,
    PdfPage,
    _image_mime,
    convert_file,
    convert_image,
    convert_pdf_pages,
    convert_table,
    convert_text,
    extract_pdf_pages,
)


def _pdf_com_texto(*textos: str) -> bytes:
    """Gera um PDF em memória com um texto por página (via PyMuPDF)."""
    document = pymupdf.open()
    for texto in textos:
        page = document.new_page()
        page.insert_text((72, 72), texto)
    data = document.tobytes()
    document.close()
    return data


def test_extract_pdf_pages_texto_e_imagem_por_pagina_em_ordem():
    pages = extract_pdf_pages(_pdf_com_texto("PAGINA UM", "PAGINA DOIS"))

    assert [page.number for page in pages] == [1, 2]
    assert "PAGINA UM" in pages[0].text
    assert "PAGINA DOIS" in pages[1].text
    assert pages[0].image is not None and pages[0].image.startswith(b"\x89PNG")
    assert pages[1].image is not None and pages[1].image.startswith(b"\x89PNG")
    assert pages[0].image != pages[1].image


def test_extract_pdf_pages_sem_poppler_usa_pypdf_e_pymupdf(monkeypatch):
    monkeypatch.setattr("chat_csa.kb_convert.shutil.which", lambda name: None)

    pages = extract_pdf_pages(_pdf_com_texto("SEM POPPLER"))

    assert len(pages) == 1
    assert "SEM POPPLER" in pages[0].text
    assert pages[0].image is not None and pages[0].image.startswith(b"\x89PNG")


def test_convert_pdf_pages_lotes_texto_imagens_e_ordem():
    pages = [PdfPage(number=i, text=f"texto {i}", image=f"img-{i}".encode()) for i in range(1, 6)]
    calls: list[tuple[str, list[bytes]]] = []

    def fake_call(prompt: str, images: list[bytes]) -> str:
        calls.append((prompt, images))
        return f"## página {len(calls)}"

    markdown = convert_pdf_pages(pages, fake_call, pages_per_call=2)

    assert [len(images) for _, images in calls] == [2, 2, 1]
    assert "esqueleto" in calls[0][0]
    assert "Página 1 — texto extraído" in calls[0][0]
    assert "texto 2" in calls[0][0]
    assert "texto 3" in calls[1][0]
    assert "As imagens anexadas, na ordem, são as páginas 5." in calls[2][0]
    assert calls[2][1] == [b"img-5"]
    assert markdown == "## página 1\n\n## página 2\n\n## página 3"


def test_convert_pdf_pages_falha_sem_markdown():
    with pytest.raises(ConversionError):
        convert_pdf_pages([PdfPage(number=1, text="", image=b"x")], lambda prompt, images: "  ")


def test_convert_image_usa_a_chamada_multimodal_com_texto_vazio():
    calls: list[tuple[str, list[bytes]]] = []

    def fake_call(prompt: str, images: list[bytes]) -> str:
        calls.append((prompt, images))
        return "# Imagem"

    markdown = convert_image(b"\x89PNG-fake", fake_call)

    assert markdown == "# Imagem"
    assert calls[0][1] == [b"\x89PNG-fake"]
    assert "Não há texto extraído" in calls[0][0]
    assert "nunca invente" in calls[0][0].lower()


def test_convert_table_csv_e_tsv_viram_tabela_markdown():
    esperado = "| nome | idade |\n| --- | --- |\n| Ana | 20 |"

    assert convert_table("dados.csv", b"nome,idade\nAna,20\n") == esperado
    assert convert_table("dados.tsv", b"nome\tidade\nAna\t20\n") == esperado


def test_convert_text_md_txt_json_direto_sem_frontmatter():
    assert convert_text("nota.txt", b"linha um\nlinha dois") == "linha um\nlinha dois"
    assert convert_text("nota.md", b"---\nold: 1\n---\n\n# Titulo\n\ncorpo") == "# Titulo\n\ncorpo"
    assert convert_text("dados.json", b'{"a": 1}') == '{"a": 1}'

    with pytest.raises(ConversionError):
        convert_text("binario.md", b"\x00\x01")


def test_convert_file_tipo_nao_suportado_tem_motivo():
    resultado = convert_file("planilha.xlsx", b"PK", lambda prompt, images: "x")

    assert not resultado.converted
    assert resultado.error is not None and "sem conversão" in resultado.error


def test_convert_file_falha_nao_interrompe_os_demais():
    def call_quebrado(prompt: str, images: list[bytes]) -> str:
        raise RuntimeError("modelo fora do ar")

    arquivos = [("planilha.xlsx", b"a"), ("foto.png", b"b"), ("nota.txt", b"conteudo")]
    resultados = [convert_file(path, content, call_quebrado) for path, content in arquivos]

    assert [resultado.converted for resultado in resultados] == [False, False, True]
    assert resultados[1].error is not None and "modelo fora do ar" in resultados[1].error


def test_default_model_call_usa_llm_do_servico_e_override(monkeypatch):
    from chat_csa import kb_convert
    from chat_csa.agent import factory

    capturado: dict = {}

    class FakeLLM:
        def invoke(self, messages):
            capturado["messages"] = messages
            return type("Resposta", (), {"content": "# convertido"})()

    def fake_get_llm(provider=None, model=None, temperature=0.2):
        capturado["model"] = model
        return FakeLLM()

    monkeypatch.setattr(factory, "get_llm", fake_get_llm)
    monkeypatch.delenv("KB_CONVERT_MODEL", raising=False)

    call = kb_convert.default_model_call()
    assert call("prompt", [b"\x89PNG-fake"]) == "# convertido"
    assert capturado["model"] is None  # sem override vale o LLM_MODEL do serviço

    mensagem = capturado["messages"][0]
    assert mensagem.content[0] == {"type": "text", "text": "prompt"}
    assert mensagem.content[1]["type"] == "image_url"
    assert mensagem.content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    monkeypatch.setenv("KB_CONVERT_MODEL", "modelo-de-conversao")
    kb_convert.default_model_call()
    assert capturado["model"] == "modelo-de-conversao"


def test_image_mime_detecta_png_jpeg_e_gif():
    assert _image_mime(b"\x89PNG-fake") == "image/png"
    assert _image_mime(b"\xff\xd8\xff-fake") == "image/jpeg"
    assert _image_mime(b"GIF89a-fake") == "image/gif"