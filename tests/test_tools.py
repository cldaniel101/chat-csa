"""Ferramentas do consumer: kb_list/kb_read no backend local (sem rede).

Cobrem a renderização por tipo — texto, csv→tabela Markdown, pdf→texto e
binário→aviso — e a composição do prompt.
"""

from pathlib import Path

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


def _portal_skill(root: Path) -> None:
    """Skill de teste que exige o portal (requires: portal)."""
    skills = root / "skills" / "portal-demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: portal-demo\nrequires: portal\n---\n# Portal demo web_csa_search",
        encoding="utf-8",
    )


def test_prompt_sem_portal_nao_anuncia_web_csa(tmp_path, monkeypatch):
    """Com o portal desligado o prompt não pode citar `web_csa_*`: o modelo
    tenta chamar a ferramenta, ela não está registrada e a UI mostra um passo
    com erro (regressão observada no preview de 27/09/2026)."""
    monkeypatch.delenv("CHAT_CSA_PORTAL_TOOLS", raising=False)
    (tmp_path / "AGENTS.md").write_text("# Test agents")
    _portal_skill(tmp_path)

    prompt = build_system_prompt(tmp_path)

    assert "Portal demo" not in prompt
    assert "web_csa" not in prompt
    assert "não tente chamar nenhuma que não esteja lá" in prompt


def test_prompt_com_portal_inclui_a_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_CSA_PORTAL_TOOLS", "1")
    (tmp_path / "AGENTS.md").write_text("# Test agents")
    _portal_skill(tmp_path)

    prompt = build_system_prompt(tmp_path)

    assert "Portal demo" in prompt
    assert "web_csa_search" in prompt


def test_prompt_do_consumer_real_nao_cita_web_csa(monkeypatch):
    """Regressão no config real: `chat-csa print-prompt` com o portal desligado
    não pode conter nenhuma menção a `web_csa_*`."""
    monkeypatch.delenv("CHAT_CSA_PORTAL_TOOLS", raising=False)
    root = Path(__file__).resolve().parents[1] / ".consumer"

    prompt = build_system_prompt(root)

    assert "web_csa" not in prompt
