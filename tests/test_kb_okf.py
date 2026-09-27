"""Testes dos conceitos OKF e índices (`chat_csa.kb_okf`)."""

from __future__ import annotations

import pytest

from chat_csa.kb_okf import (
    InvalidPathError,
    build_concept,
    concept_path_for,
    normalize_declared_path,
    section_of,
    update_root_index,
    update_section_index,
)

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


def test_build_concept_segue_o_template_e_deriva_os_campos():
    markdown = "# Edital de Matrícula\n\nPrimeiro parágrafo do documento com o resumo."
    concept = build_concept(
        markdown,
        path="editais/sisu_edital.pdf",
        template_text=TEMPLATE,
        timestamp="2026-09-27",
    )

    assert 'type: "Documento PDF"' in concept
    assert 'title: "Edital de Matrícula"' in concept
    assert 'description: "Primeiro parágrafo do documento com o resumo."' in concept
    assert 'tags: [sisu-2026, "editais"]' in concept
    assert 'timestamp: "2026-09-27"' in concept
    # Ordem do template preservada.
    assert (
        concept.index("type:")
        < concept.index("title:")
        < concept.index("description:")
        < concept.index("tags:")
        < concept.index("timestamp:")
    )
    # Sem citação: os campos de citação ficam omitidos.
    assert "resource:" not in concept
    assert "url:" not in concept
    assert "source_page:" not in concept
    # Corpo preservado, sem duplicar o título.
    assert concept.count("# Edital de Matrícula") == 1
    assert "Primeiro parágrafo do documento com o resumo." in concept


def test_build_concept_sem_heading_deriva_titulo_da_primeira_linha():
    concept = build_concept(
        "**Guia** de [uso](http://exemplo) do sistema\n\nCorpo.",
        path="manuais/guia.txt",
        template_text=TEMPLATE,
        timestamp="2026-09-27",
    )

    assert 'title: "Guia de uso do sistema"' in concept
    assert "# Guia de uso do sistema" in concept
    assert 'type: "Texto"' in concept


def test_build_concept_descricao_de_fallback_e_chaves_padrao_sem_template():
    concept = build_concept(
        "# Só Título",
        path="editais/x.pdf",
        template_text=None,
        timestamp="2026-09-27",
    )

    assert 'description: "Documento enviado por upload (x.pdf)."' in concept
    assert 'type: "Documento PDF"' in concept


def test_build_concept_com_citacao_declarada():
    concept = build_concept(
        "# Edital\n\nCorpo do edital.",
        path="editais/edital.pdf",
        source="https://csa.uefs.br/edital.pdf",
        template_text=TEMPLATE,
        timestamp="2026-09-27",
    )

    assert 'resource: "https://csa.uefs.br/edital.pdf"' in concept
    assert 'url: "https://csa.uefs.br/edital.pdf"' in concept
    assert 'source_page: "https://csa.uefs.br/edital.pdf"' in concept
    assert "# Citations" in concept
    assert "[1] [Edital](https://csa.uefs.br/edital.pdf)" in concept
    # A citação entra depois do corpo.
    assert concept.index("Corpo do edital.") < concept.index("# Citations")


def test_concept_path_for_e_section_of():
    assert concept_path_for("editais/edital_2026.PDF") == "editais/edital_2026.md"
    assert concept_path_for("a/b/c.txt") == "a/b/c.md"
    assert section_of("editais/edital.pdf") == "editais"
    assert section_of("nota.md") == ""


def test_normalize_declared_path_normaliza_caracteres_e_extensao():
    assert normalize_declared_path("editais/Edital 2026.PDF") == "editais/Edital-2026.md"
    assert normalize_declared_path("matricula\\nota.txt") == "matricula/nota.md"
    assert normalize_declared_path("a/b/c") == "a/b/c.md"

    for invalido in [
        "",
        "/abs/x.pdf",
        "sem_pasta.pdf",
        "editais/../x.pdf",
        ".okf/x.pdf",
        "a//b.pdf",
    ]:
        with pytest.raises(InvalidPathError):
            normalize_declared_path(invalido)


def test_build_concept_sem_citacao_omite_campos_e_secao():
    concept = build_concept(
        "# Nota\n\nCorpo.",
        path="manuais/nota.txt",
        template_text=TEMPLATE,
        timestamp="2026-09-27",
    )

    assert "resource:" not in concept
    assert "url:" not in concept
    assert "source_page:" not in concept
    assert "Citations" not in concept


def test_update_section_index_cria_secao_nova_com_bullet():
    index = update_section_index(
        None,
        section="novidades",
        title="Aviso",
        concept_path="novidades/aviso.md",
        description="Curto.",
    )

    assert index == "# novidades\n\n* [Aviso](novidades/aviso.md) - Curto.\n"


def test_update_section_index_atualiza_bullet_sem_duplicar_e_preserva_autoral():
    existente = (
        "# editais\n\nAutorais aqui.\n\n"
        "* [Outro](editais/outro.md) - Outro.\n\n"
        "* [Antigo](editais/x.md) - velho\n"
    )
    atualizado = update_section_index(
        existente,
        section="editais",
        title="Novo",
        concept_path="editais/x.md",
        description="novo resumo",
    )

    assert atualizado.count("editais/x.md") == 1
    assert "* [Novo](editais/x.md) - novo resumo" in atualizado
    assert "* [Outro](editais/outro.md) - Outro." in atualizado
    assert "Autorais aqui." in atualizado
    assert atualizado.endswith("\n")


def test_update_section_index_acrescenta_bullet_novo():
    existente = "# editais\n\n* [Outro](editais/outro.md) - Outro.\n"
    atualizado = update_section_index(
        existente,
        section="editais",
        title="Y",
        concept_path="editais/y.md",
        description="y",
    )

    assert atualizado.endswith("* [Y](editais/y.md) - y\n")
    assert atualizado.count("* [") == 2


ROOT_INDEX = (
    "# Base de conhecimento\n\nIntro autoral.\n\n"
    "## Editais, resoluções e instruções normativas\n\n"
    "* [Edital A](editais/a.md) - A.\n\n"
    "## Documentos de matrícula, declarações e recursos\n\n"
    "* [Declaração B](matricula/b.md) - B.\n"
)


def test_update_root_index_insere_na_secao_correspondente():
    atualizado = update_root_index(
        ROOT_INDEX,
        section="editais",
        title="Novo",
        concept_path="editais/novo.md",
        description="Novo.",
    )

    assert "* [Novo](editais/novo.md) - Novo." in atualizado.splitlines()
    assert atualizado.index("* [Novo](editais/novo.md)") < atualizado.index("## Documentos de matrícula")
    assert "* [Edital A](editais/a.md) - A." in atualizado
    assert "Intro autoral." in atualizado


def test_update_root_index_cria_secao_nova():
    atualizado = update_root_index(
        ROOT_INDEX,
        section="novidades",
        title="Aviso",
        concept_path="novidades/aviso.md",
        description="Aviso.",
    )

    assert "## novidades" in atualizado
    assert atualizado.rstrip().endswith("* [Aviso](novidades/aviso.md) - Aviso.")
    assert "Intro autoral." in atualizado


def test_update_root_index_substitui_bullet_de_sobrescrita():
    atualizado = update_root_index(
        ROOT_INDEX,
        section="editais",
        title="Edital A v2",
        concept_path="editais/a.md",
        description="A.",
    )

    assert atualizado.count("editais/a.md") == 1
    assert "* [Edital A v2](editais/a.md) - A." in atualizado
    assert "## Documentos de matrícula" in atualizado