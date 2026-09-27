"""Conceitos OKF e índices da base (mesmo formato do bundle `data`).

O upload grava cada arquivo convertido como um conceito `.md`:

    ---
    type: "Documento PDF"
    title: "..."
    description: "..."
    tags: [sisu-2026, "<seção>"]
    timestamp: "AAAA-MM-DD"
    ---

    # Título

    <corpo convertido>

Os campos de citação (`resource`, `url`, `source_page`) e a seção `# Citations`
só entram quando o remetente declara a fonte. Os índices (raiz e da seção) são
atualizados no mesmo commit, no formato
`* [Título](caminho.md) - descrição curta`.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import PurePosixPath

from .kb_convert import conversion_kind

OKF_CONTENT_TEMPLATE = ".okf/template/content.md"
OKF_INDEX_TEMPLATE = ".okf/template/index.md"

# Fallback quando o template não está disponível: mesmas chaves e ordem.
DEFAULT_FRONTMATTER_KEYS = (
    "type",
    "title",
    "description",
    "resource",
    "url",
    "source_page",
    "tags",
    "timestamp",
)

_DOC_TYPES = {
    "pdf": "Documento PDF",
    "image": "Imagem",
    "table": "Planilha",
    "text": "Texto",
}


class InvalidPathError(ValueError):
    """Caminho declarado inválido para virar conceito."""


# ---------------------------------------------------------------------------
# Caminho e seção
# ---------------------------------------------------------------------------

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_declared_path(path: str) -> str:
    """Normaliza o caminho declarado no upload para `<pasta>/<slug>.md`.

    - sempre relativo, com ao menos uma pasta (a seção);
    - sem `..`, segmentos vazios ou ocultos (`.okf/...`);
    - caracteres normalizados por segmento (NFC, espaços viram `-`);
    - a extensão original é trocada por `.md`.
    """
    raw = (path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        raise InvalidPathError("o caminho deve ser relativo")
    parts = raw.split("/")
    if len(parts) < 2:
        raise InvalidPathError("inclua a pasta da seção (ex.: editais/arquivo.pdf)")
    normalized: list[str] = []
    for part in parts:
        if _CONTROL_CHARS_RE.search(part):
            raise InvalidPathError("caractere de controle no caminho")
        segment = _WHITESPACE_RE.sub("-", unicodedata.normalize("NFC", part).strip())
        if not segment or segment in {".", ".."}:
            raise InvalidPathError("segmento de caminho inválido")
        if segment.startswith("."):
            raise InvalidPathError("segmentos ocultos não são aceitos")
        normalized.append(segment)
    return str(PurePosixPath("/".join(normalized)).with_suffix(".md"))


def concept_path_for(path: str) -> str:
    """Caminho do conceito: `<pasta>/<slug>.md` (extensão trocada)."""
    return str(PurePosixPath(path).with_suffix(".md"))


def section_of(path: str) -> str:
    """Pasta do caminho declarado (a seção do conceito)."""
    parent = PurePosixPath(path).parent
    return "" if str(parent) == "." else str(parent)


def doc_type_for(path: str) -> str:
    """Tipo do conceito pelo arquivo de origem (ex.: `Documento PDF`)."""
    kind = conversion_kind(path)
    return _DOC_TYPES.get(kind or "", "Documento")


# ---------------------------------------------------------------------------
# Conceito: frontmatter + corpo
# ---------------------------------------------------------------------------


def build_concept(
    markdown: str,
    *,
    path: str,
    source: str | None = None,
    template_text: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Monta o conceito OKF do arquivo declarado (`path` é o caminho de origem)."""
    title, description = concept_metadata(markdown, path)
    values = {
        "type": _yaml_scalar(doc_type_for(path)),
        "title": _yaml_scalar(title),
        "description": _yaml_scalar(description),
        "resource": _yaml_scalar(source) if source else None,
        "url": _yaml_scalar(source) if source else None,
        "source_page": _yaml_scalar(source) if source else None,
        "tags": _tags_value(section_of(path)),
        "timestamp": _yaml_scalar(timestamp or date.today().isoformat()),
    }
    lines = ["---"]
    for key in frontmatter_keys(template_text):
        rendered = values.get(key)
        if rendered is not None:
            lines.append(f"{key}: {rendered}")
    lines.append("---")

    body = markdown.strip()
    if not _starts_with_heading(body):
        body = f"# {title}\n\n{body}"
    document = "\n".join(lines) + "\n\n" + body
    if source:
        document += f"\n\n# Citations\n\n[1] [{title}]({source})"
    return document + "\n"


def frontmatter_keys(template_text: str | None) -> tuple[str, ...]:
    """Ordem das chaves do frontmatter conforme o template OKF da base."""
    if not template_text:
        return DEFAULT_FRONTMATTER_KEYS
    match = re.match(r"\A---[ \t]*\n(.*?)\n---", template_text, re.DOTALL)
    if not match:
        return DEFAULT_FRONTMATTER_KEYS
    keys = tuple(
        line.split(":", 1)[0].strip()
        for line in match.group(1).splitlines()
        if ":" in line and not line.strip().startswith("#")
    )
    return keys or DEFAULT_FRONTMATTER_KEYS


def concept_metadata(markdown: str, path: str) -> tuple[str, str]:
    """Título e descrição derivados do documento (frontmatter e índices)."""
    title = derive_title(markdown, fallback=PurePosixPath(path).stem)
    description = derive_description(
        markdown,
        fallback=f"Documento enviado por upload ({PurePosixPath(path).name}).",
    )
    return title, description


def derive_title(markdown: str, *, fallback: str) -> str:
    """Título do próprio documento: primeiro H1 ou primeira linha com texto."""
    heading = _first_heading(markdown)
    if heading:
        return heading
    for line in markdown.splitlines():
        candidate = _plain_text(line)
        if candidate:
            return _truncate(candidate, 120)
    return fallback


def derive_description(markdown: str, *, fallback: str) -> str:
    """Descrição curta: primeiro parágrafo com texto; senão, o fallback."""
    for line in markdown.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if set(candidate) <= {"-", "*", "_", " "}:
            continue
        candidate = _plain_text(candidate)
        if candidate:
            return _truncate(candidate, 160)
    return fallback


# ---------------------------------------------------------------------------
# Helpers de texto e YAML
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*#*\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKS_RE = re.compile(r"[*_`~]+")


def _first_heading(markdown: str) -> str | None:
    match = _HEADING_RE.search(markdown)
    return match.group(1).strip() if match else None


def _starts_with_heading(markdown: str) -> bool:
    for line in markdown.splitlines():
        if not line.strip():
            continue
        return line.lstrip().startswith("# ")
    return False


def _plain_text(line: str) -> str:
    text = _LINK_RE.sub(r"\1", line)
    text = _MARKS_RE.sub("", text)
    return text.strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return cut + "…"


def _yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _tags_value(section: str) -> str:
    if not section:
        return "[sisu-2026]"
    return f'[sisu-2026, "{section}"]'


# ---------------------------------------------------------------------------
# Índices (raiz e da seção)
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^\s*\*\s+\[[^\]]*\]\(([^)]*)\)\s*-\s*.*$")


def bullet_for(title: str, concept_path: str, description: str) -> str:
    """Bullet do índice: `* [Título](caminho.md) - descrição curta`."""
    safe_title = title.replace("[", "\\[").replace("]", "\\]")
    safe_description = " ".join(description.split())
    return f"* [{safe_title}]({concept_path}) - {safe_description}"


def update_section_index(
    existing: str | None,
    *,
    section: str,
    title: str,
    concept_path: str,
    description: str,
) -> str:
    """Index.md da seção com exatamente um bullet do conceito.

    `existing` é o texto atual da seção (None cria o índice do zero, para
    seção nova); um bullet do mesmo caminho é substituído, não duplicado.
    """
    bullet = bullet_for(title, concept_path, description)
    if existing is None or not existing.strip():
        return f"# {section}\n\n{bullet}\n"
    lines = existing.rstrip("\n").split("\n")
    matches = [
        index
        for index, line in enumerate(lines)
        if (match := _BULLET_RE.match(line)) and match.group(1).strip() == concept_path
    ]
    if matches:
        lines[matches[0]] = bullet
        for index in reversed(matches[1:]):
            del lines[index]
        return "\n".join(lines) + "\n"
    lines.append(bullet)
    return "\n".join(lines) + "\n"


_HEADING_LINE_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*$")


def _normalize_heading(text: str) -> str:
    """Minúsculas sem acento, para casar `matricula` com `Matrícula`."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _section_heading_index(lines: list[str], section: str) -> int | None:
    needle = _normalize_heading(section)
    if not needle:
        return None
    for index, line in enumerate(lines):
        heading = _HEADING_LINE_RE.match(line)
        if heading and needle in _normalize_heading(heading.group(2)):
            return index
    return None


def update_root_index(
    existing: str,
    *,
    section: str,
    title: str,
    concept_path: str,
    description: str,
) -> str:
    """Índice raiz com o bullet do conceito na seção correspondente.

    Substitui o bullet do mesmo caminho (sobrescrita), insere no fim da seção
    existente ou cria a seção nova — sem tocar no texto autoral.
    """
    bullet = bullet_for(title, concept_path, description)
    lines = existing.rstrip("\n").split("\n") if existing.strip() else []

    # 1. Bullet do mesmo caminho em qualquer seção: substitui e deduplica.
    matches = [
        index
        for index, line in enumerate(lines)
        if (match := _BULLET_RE.match(line)) and match.group(1).strip() == concept_path
    ]
    if matches:
        lines[matches[0]] = bullet
        for index in reversed(matches[1:]):
            del lines[index]
        return "\n".join(lines) + "\n"

    # 2. Seção correspondente: insere no fim do bloco, antes das linhas vazias.
    heading_index = _section_heading_index(lines, section)
    if heading_index is not None:
        block_end = len(lines)
        for index in range(heading_index + 1, len(lines)):
            if _HEADING_LINE_RE.match(lines[index]):
                block_end = index
                break
        insert_at = block_end
        while insert_at > heading_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, bullet)
        return "\n".join(lines) + "\n"

    # 3. Seção nova: heading + bullet ao final.
    if lines and lines[-1].strip():
        lines.append("")
    if section:
        lines += [f"## {section}", ""]
    lines.append(bullet)
    return "\n".join(lines) + "\n"