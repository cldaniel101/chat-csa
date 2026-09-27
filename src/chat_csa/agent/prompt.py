"""Carregador de prompt: compõe AGENTS.md + skills em um system prompt.

O design espelha o layout .agents do pi, mas enraizado no diretório de
config do agente (padrão: .consumer). Layout:

    {root}/
      AGENTS.md               # instruções opcionais do projeto
      skills/
        <skill-name>/
          SKILL.md            # descrição da skill
          ...                 # outros arquivos ignorados

Todo markdown encontrado é concatenado em um único system prompt, que é
anteposto à mensagem de sistema do LLM.

Você pode colocar o que quiser dentro de .consumer — ele é o "AGENTS home"
do agente. Em runtime o agente o lê fresco a cada request (sem cache),
então dá para editar skills a quente sem reiniciar.
"""

from __future__ import annotations

from pathlib import Path


def load_agents_md(root: Path) -> str | None:
    for name in ("AGENTS.md", "AGENTS.MD", "agents.md"):
        p = root / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
    return None


def load_skills(root: Path) -> list[tuple[str, str]]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            # também aceita .md com nome da skill
            candidates = list(child.glob("*.md"))
            if not candidates:
                continue
            skill_md = candidates[0]
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        out.append((child.name, content))
    return out


def build_system_prompt(root: Path, extra: str | None = None) -> str:
    parts: list[str] = []

    # Identidade base
    parts.append(
        textwrap_dedent(
            """
            Você é o agente consumer do Chat CSA: responde perguntas sobre SISU/UEFS
            a partir da base de conhecimento remota, nunca alucinando.
            - Use kb_list/kb_read para consultar a base antes de afirmar qualquer fato.
            - Cite sempre a URL do frontmatter (`resource:`/`url:`) da fonte — nunca o caminho do arquivo.
            - Seja conciso e nunca invente prazos, documentos ou datas.
            - Se uma ferramenta falhar, explique o erro e responda com o que foi possível confirmar.
            """
        ).strip()
    )

    agents_md = load_agents_md(root)
    if agents_md:
        parts.append(f"# Project Instructions ({root}/AGENTS.md)\n\n{agents_md.strip()}")

    skills = load_skills(root)
    if skills:
        parts.append(f"# Skills loaded from {root}/skills/ ({len(skills)} found)")
        for name, content in skills:
            parts.append(f"## Skill: {name}\n\n{content.strip()}")

    if extra:
        parts.append(extra.strip())

    # Dica de uso das ferramentas (web_csa_* só quando ligadas)
    portal_on = __import__("os").getenv("CHAT_CSA_PORTAL_TOOLS", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
    tool_lines = [
        "# Ferramentas",
        "- kb_list(prefix): lista os caminhos disponíveis na base de conhecimento remota",
        "- kb_read(path): lê um arquivo da base (csv/tsv -> tabela, pdf -> texto, binário -> aviso)",
    ]
    if portal_on:
        tool_lines += [
            "- web_csa_search(query, categoria, since, limit): busca no catálogo do portal CSA/UEFS",
            "- web_csa_fetch(url, refresh, extract_text): abre uma página/PDF do portal (allowlist csa.uefs.br)",
        ]
    tool_lines += [
        "",
        "Sempre consulte a base com kb_list/kb_read antes de responder perguntas factuais.",
        "Cite a URL do frontmatter (`resource:`/`url:`) da fonte — nunca o caminho do arquivo.",
    ]
    parts.append("\n".join(tool_lines))

    return "\n\n---\n\n".join(parts)


def textwrap_dedent(s: str) -> str:
    import textwrap

    return textwrap.dedent(s)
