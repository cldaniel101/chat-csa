"""Carregador de prompt: compõe AGENTS.md + skills em um system prompt.

O design espelha o layout .agents do pi, mas enraizado em um diretório
arbitrário (.ingester / .consumer). Layout:

    {root}/
      AGENTS.md               # instruções opcionais do projeto
      skills/
        <skill-name>/
          SKILL.md            # descrição da skill
          ...                 # outros arquivos ignorados

Todo markdown encontrado é concatenado em um único system prompt, que é
anteposto à mensagem de sistema do LLM.

Você pode colocar o que quiser dentro de .ingester ou .consumer — eles
são o "AGENTS home" de cada agente. Em runtime o agente os lê frescos a
cada request (sem cache), então dá para editar skills a quente sem reiniciar.
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
            Você é um agente de IA prestativo com acesso a ferramentas de filesystem: read, write, edit, bash.
            - Use ferramentas quando precisar inspecionar ou modificar arquivos, ou executar comandos.
            - Seja conciso, cite fontes ao responder a partir de arquivos e nunca alucine.
            - Se uma operação de arquivo falhar, explique o erro e sugira uma correção.
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

    # Dica de uso das ferramentas
    parts.append(
        textwrap_dedent(
            """
            # Ferramentas
            - read(path): lê um arquivo de texto (truncado para 50KB/2000 linhas)
            - write(path, content): cria/sobrescreve um arquivo (cria os diretórios pais)
            - edit(path, oldText, newText): substituição exata de texto (oldText deve ser único)
            - bash(command, timeout=30): executa um comando de shell

            Prefira edit() para mudanças pequenas e write() para arquivos novos.
            Use bash() para ls, grep, find, git etc.
            """
        ).strip()
    )

    return "\n\n---\n\n".join(parts)


def textwrap_dedent(s: str) -> str:
    import textwrap

    return textwrap.dedent(s)
