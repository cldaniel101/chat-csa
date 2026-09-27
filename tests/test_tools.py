"""Ferramentas do consumer: kb_list/kb_read no backend local (sem rede).

Cobrem a renderização por tipo — texto, csv→tabela Markdown, pdf→texto e
binário→aviso — e a composição do prompt.
"""

from test_csa_portal import _pdf_with_text

from chat_csa.agent.prompt import build_system_prompt
from chat_csa.agent.tools import kb_list, kb_read


def test_kb_list_and_read_text(kb_local):
    target = kb_local / "perguntas-frequentes"
    target.mkdir()
    (target / "faq.md").write_text("# FAQ\n\nO prazo é 10/10.\n", encoding="utf-8")

    listing = kb_list.invoke({"prefix": "perguntas"})
    assert "perguntas-frequentes/faq.md" in listing

    text = kb_read.invoke({"path": "perguntas-frequentes/faq.md"})
    assert "O prazo é 10/10." in text


def test_kb_read_csv_renders_markdown_table(kb_local):
    (kb_local / "dados.csv").write_text("nome,nota\nAna,900\n", encoding="utf-8")

    out = kb_read.invoke({"path": "dados.csv"})

    assert "| nome | nota |" in out
    assert "| Ana | 900 |" in out


def test_kb_read_pdf_extracts_text(kb_local):
    (kb_local / "edital.pdf").write_bytes(_pdf_with_text("Texto extraivel CSA UEFS"))

    out = kb_read.invoke({"path": "edital.pdf"})

    assert "Texto extraivel CSA UEFS" in out


def test_kb_read_binary_returns_notice(kb_local):
    (kb_local / "binario.bin").write_bytes(b"\x00\x01\x02\x03")

    out = kb_read.invoke({"path": "binario.bin"})

    assert "Aviso" in out
    assert "binário" in out
    assert "application/octet-stream" in out
    assert "4 bytes" in out


def test_kb_read_missing_returns_error(kb_local):
    out = kb_read.invoke({"path": "nao-existe.md"})

    assert out.startswith("Error:")
    assert "não encontrado" in out


def test_prompt_build(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Test agents")
    skills = tmp_path / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# Demo skill")

    prompt = build_system_prompt(tmp_path)

    assert "Test agents" in prompt
    assert "Demo skill" in prompt
