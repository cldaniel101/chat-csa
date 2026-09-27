"""Testes do processamento do upload (`chat_csa.kb_upload`)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from chat_csa.kb import KBCommit, KBFile, KBNotFoundError
from chat_csa.kb_upload import process_upload

TEMPLATE = """---
type: Documento PDF
title: "<título do documento>"
description: "<resumo de uma frase sobre o documento>"
resource: "<URL real do PDF de origem>"
url: "<URL real do PDF de origem>"
source_page: "<URL da página que lista o PDF>"
tags: [sisu-2026, "<categoria>"]
timestamp: "<AAAA-MM-DD>"
---

# <Título do documento>
"""

ROOT_INDEX = (
    "# Base de conhecimento\n\n"
    "## Editais, resoluções e instruções normativas\n\n"
    "* [Antigo](editais/antigo.md) - Antigo.\n"
)


class FakeKB:
    """Base em memória com a interface usada pelo upload (list/read/write)."""

    def __init__(self, files: Mapping[str, str] | None = None):
        self.files: dict[str, str] = dict(files or {})
        self.writes: list[tuple[list[tuple[str, str]], str]] = []

    def list(self, prefix: str = "") -> list[str]:
        return sorted(path for path in self.files if path.startswith(prefix))

    def read(self, path: str) -> KBFile:
        if path not in self.files:
            raise KBNotFoundError(f"não encontrado: {path}")
        return KBFile(path=path, content=self.files[path].encode("utf-8"), content_type="text/markdown")

    def write(
        self,
        files: Mapping[str, str] | Sequence[tuple[str, str]],
        message: str,
    ) -> KBCommit:
        items = list(files.items()) if isinstance(files, Mapping) else list(files)
        for path, content in items:
            self.files[path] = content
        self.writes.append(([(path, content) for path, content in items], message))
        return KBCommit(sha="fake-sha", paths=tuple(path for path, _ in items))


def _kb() -> FakeKB:
    return FakeKB(
        {
            ".okf/template/content.md": TEMPLATE,
            "index.md": ROOT_INDEX,
            "editais/antigo.md": "# Antigo\n",
        }
    )


def test_process_upload_rejeita_invalido_e_duplicado_sem_commitar():
    kb = _kb()
    payload = [
        ("editais/ok.txt", b"conteudo do arquivo"),
        ("sem_pasta.txt", b"x"),
        ("editais/../x.txt", b"x"),
        ("editais/ok.txt", b"repetido"),
    ]

    resultado = process_upload(kb, payload, model_call=lambda prompt, images: "stub", message="teste")

    assert [file.path for file in resultado.files] == [path for path, _ in payload]
    ok, invalido, relativo, duplicado = resultado.files
    assert ok.ok and ok.converted
    assert not invalido.ok and not invalido.converted and "caminho inválido" in (invalido.error or "")
    assert not relativo.ok and not relativo.converted and "caminho inválido" in (relativo.error or "")
    assert not duplicado.ok and not duplicado.converted and "duplicado" in (duplicado.error or "")

    committed = [path for path, _ in kb.writes[-1][0]]
    assert committed == ["editais/ok.md", "index.md"]


def test_process_upload_grava_no_caminho_normalizado():
    kb = _kb()

    resultado = process_upload(
        kb,
        [("editais/Relatório 2026.csv", b"nome,qtd\nA,1\n")],
        model_call=lambda prompt, images: "stub",
    )

    assert resultado.files[0].converted
    assert [path for path, _ in kb.writes[-1][0]] == ["editais/Relatório-2026.md", "index.md"]
    assert "editais/Relatório-2026.md" in kb.files


def test_process_upload_converte_antes_de_commitar():
    kb = _kb()
    eventos: list[str] = []

    def model_call(prompt: str, images: list[bytes]) -> str:
        eventos.append("conversao")
        return "# Foto"

    original_write = kb.write

    def write_spy(files, message):  # type: ignore[no-untyped-def]
        eventos.append("commit")
        return original_write(files, message)

    kb.write = write_spy  # type: ignore[method-assign]

    process_upload(kb, [("editais/foto.png", b"\x89PNG-fake")], model_call=model_call)

    assert eventos == ["conversao", "commit"]


def test_process_upload_sem_conversao_nao_entra_no_commit():
    kb = _kb()

    def model_call(prompt: str, images: list[bytes]) -> str:
        raise RuntimeError("modelo fora")

    payload = [
        ("editais/ok.txt", b"texto convertido"),
        ("editais/planilha.xlsx", b"PK-binario"),
        ("editais/foto.png", b"\x89PNG-fake"),
    ]
    resultado = process_upload(kb, payload, model_call=model_call, message="lote misto")

    ok, nao_suportado, falhou = resultado.files
    assert ok.converted is True
    assert nao_suportado.ok is True and nao_suportado.converted is False
    assert "sem conversão" in (nao_suportado.error or "")
    assert falhou.ok is True and falhou.converted is False
    assert "modelo fora" in (falhou.error or "")

    committed = [path for path, _ in kb.writes[-1][0]]
    assert committed == ["editais/ok.md", "index.md"]
    assert "editais/foto.md" not in kb.files
    assert "editais/planilha.md" not in kb.files
    assert nao_suportado.as_dict()["converted"] is False


def test_process_upload_acima_do_orcamento_fica_converted_false_sem_commit():
    kb = _kb()

    resultado = process_upload(
        kb,
        [("editais/grande.txt", b"x" * 11)],
        model_call=lambda prompt, images: "stub",
        max_bytes=10,
    )

    assert resultado.files[0].converted is False
    assert "orçamento" in (resultado.files[0].error or "")
    assert resultado.sha is None
    assert kb.writes == []


def test_process_upload_um_unico_commit_com_conceitos_e_indices():
    kb = _kb()
    payload = [
        ("editais/a.txt", b"# A\n\nAaa."),
        ("editais/b.txt", b"# B\n\nBbb."),
        ("novidades/c.txt", b"# C\n\nCcc."),
    ]

    resultado = process_upload(kb, payload, model_call=lambda prompt, images: "stub", message="lote")

    assert len(kb.writes) == 1
    committed = [path for path, _ in kb.writes[0][0]]
    assert committed == [
        "editais/a.md",
        "editais/b.md",
        "novidades/c.md",
        "novidades/index.md",
        "index.md",
    ]
    assert resultado.sha == "fake-sha"
    assert kb.writes[0][1] == "lote"


def test_process_upload_sobrescreve_conceito_e_atualiza_o_bullet():
    kb = _kb()

    resultado = process_upload(
        kb,
        [("editais/antigo.txt", b"# Antigo\n\nnovo.")],
        model_call=lambda prompt, images: "stub",
    )

    assert resultado.files[0].converted
    assert len(kb.writes) == 1
    committed = {path for path, _ in kb.writes[0][0]}
    assert committed == {"editais/antigo.md", "index.md"}
    assert "novo." in kb.files["editais/antigo.md"]
    assert kb.files["index.md"].count("editais/antigo.md") == 1
    assert "* [Antigo](editais/antigo.md) - novo." in kb.files["index.md"]