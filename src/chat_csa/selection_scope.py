"""Detecção e validação do processo seletivo associado a uma fonte.

O filtro é aplicado no backend, independentemente das decisões do modelo. Uma
fonte de uma edição não pode ser aberta para responder sobre outra edição, e
documentos que declaram uma edição mas apontam para URLs de outra são
rejeitados integralmente.
"""

from __future__ import annotations

import contextvars
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_PROCESS_PATTERN = r"sisu|prosel|vestibular|transferencia|reingresso|portador|vagasresiduais"
_SLUG_RE = re.compile(
    rf"(?<![a-z0-9])(?P<process>{_PROCESS_PATTERN})(?P<year>\d{{2}})(?P<edition>\d)(?!\d)",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_PROCESS_YEAR_RE = re.compile(
    rf"\b(?P<process>{_PROCESS_PATTERN})\b"
    r"(?:/uefs)?\s*(?:[-–—:]\s*)?(?:(?:de|do|ano|edicao)\s+)?(?P<year>20\d{2})\b",
    re.I,
)
_YEAR_PROCESS_RE = re.compile(
    r"\b(?P<year>20\d{2})\b\s*(?:[-–—:]\s*)?(?:(?:do|no|para)\s+)?"
    rf"(?P<process>{_PROCESS_PATTERN})\b(?:/uefs)?",
    re.I,
)

_SELECTION_INTENT_TERMS = (
    "processo seletivo",
    "edital",
    "matricula",
    "documentos",
    "cota",
    "chamada",
    "lista de espera",
    "cronograma",
    "resultado",
    "inscricao",
    "nota de corte",
    "enem",
)


@dataclass(frozen=True)
class SelectionScope:
    """Escopo pedido pelo usuário ao longo da conversa."""

    process: str | None = None
    year: int | None = None
    edition: int | None = None
    selection_intent: bool = False
    needs_clarification: bool = False

    @property
    def slug(self) -> str | None:
        if not self.process or not self.year or self.edition is None:
            return None
        return f"{self.process}{self.year % 100:02d}{self.edition}"

    @property
    def label(self) -> str:
        parts = [self.process.upper() if self.process else "processo seletivo"]
        if self.year:
            parts.append(str(self.year))
        if self.edition and self.edition != 1:
            parts.append(f"edição {self.edition}")
        return " ".join(parts)

    @property
    def must_filter(self) -> bool:
        return self.selection_intent or bool(self.process or self.year)


@dataclass(frozen=True)
class SourceAssessment:
    """Edição declarada pelo documento e referências versionadas encontradas."""

    process: str | None = None
    year: int | None = None
    edition: int | None = None
    conflicting_declarations: tuple[str, ...] = ()
    mismatched_references: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if not self.process:
            return "fonte sem processo/edição identificável"
        suffix = f" {self.year}" if self.year else ""
        return f"{self.process.upper()}{suffix}"


_scope_context: contextvars.ContextVar[SelectionScope | None] = contextvars.ContextVar(
    "chat_csa_selection_scope",
    default=None,
)


def set_selection_scope(scope: SelectionScope):
    """Define o escopo da requisição atual e devolve o token para restauração."""
    return _scope_context.set(scope)


def reset_selection_scope(token) -> None:
    _scope_context.reset(token)


def get_selection_scope() -> SelectionScope | None:
    return _scope_context.get()


def infer_selection_scope(user_messages: Iterable[str]) -> SelectionScope:
    """Infere processo e edição usando a mensagem mais recente que os informa."""
    messages = [message for message in user_messages if message and message.strip()]
    process: str | None = None
    year: int | None = None
    edition: int | None = None
    selection_intent = False

    for message in reversed(messages):
        normalized = _normalize(message)
        selection_intent = selection_intent or _has_selection_intent(normalized)

        slug_match = _SLUG_RE.search(normalized)
        if slug_match:
            if process is None:
                process = _normalize_process(slug_match.group("process"))
            if year is None:
                year = 2000 + int(slug_match.group("year"))
            if edition is None:
                edition = int(slug_match.group("edition"))

        if process is None:
            process = _process_in_text(normalized)
        if year is None:
            year = _selection_year_in_text(normalized)

    if process == "sisu" and year and edition is None:
        # A nomenclatura do portal usa 1 para a edição anual: sisu261/sisu271.
        edition = 1

    needs_clarification = selection_intent and (process is None or year is None)
    return SelectionScope(
        process=process,
        year=year,
        edition=edition,
        selection_intent=selection_intent,
        needs_clarification=needs_clarification,
    )


def assess_source(path: str, text: str = "") -> SourceAssessment:
    """Confere a edição no caminho, frontmatter, corpo e URLs do documento."""
    metadata, body = _split_frontmatter(text)
    metadata_identity = "\n".join(
        value
        for key, value in metadata.items()
        if key.lower() not in {"resource", "url", "source_page"}
    )
    body_without_urls = _URL_RE.sub(" ", body[:12_000])

    declarations = (
        _scopes_in_text(path),
        _scopes_in_text(metadata_identity),
        _scopes_in_text(body_without_urls),
    )
    chosen: tuple[str, int, int | None] | None = None
    conflicts: set[str] = set()
    for candidates in declarations:
        if not candidates:
            continue
        if chosen is None:
            chosen = candidates[0]
        conflicts.update(_scope_label(candidate) for candidate in candidates if not _same_scope(candidate, chosen))

    references = []
    for url in _URL_RE.findall(text):
        cleaned = url.rstrip(".,;:)")
        reference_scopes = _scopes_in_text(cleaned)
        references.extend((cleaned, ref_scope) for ref_scope in reference_scopes)

    # Sem declaração no documento, uma URL oficial versionada ainda identifica a fonte.
    if chosen is None and references:
        chosen = references[0][1]

    mismatched: list[str] = []
    if chosen is not None:
        for url, reference in references:
            if not _same_scope(chosen, reference):
                mismatched.append(url)

    process, year, edition = chosen if chosen else (None, None, None)
    return SourceAssessment(
        process=process,
        year=year,
        edition=edition,
        conflicting_declarations=tuple(sorted(conflicts)),
        mismatched_references=tuple(dict.fromkeys(mismatched)),
    )


def source_rejection_reason(scope: SelectionScope, source: SourceAssessment) -> str | None:
    """Explica por que a fonte não pode participar da resposta atual."""
    if scope.needs_clarification:
        return (
            "a pergunta não informa processo e ano/edição; "
            "é obrigatório esclarecer isso antes de consultar fontes versionadas"
        )
    if source.conflicting_declarations:
        return "o documento contém declarações conflitantes de processo/edição"
    if source.mismatched_references:
        refs = ", ".join(source.mismatched_references[:3])
        return f"o documento {source.label} aponta para referência de outra edição: {refs}"
    if not scope.must_filter:
        return None
    if not scope.process or not scope.year:
        return "não foi possível determinar o processo e a edição solicitados"
    if not source.process or not source.year:
        return "o documento não declara processo e edição de forma verificável"
    if source.process != scope.process or source.year != scope.year:
        return f"a fonte pertence a {source.label}, mas a pergunta é sobre {scope.label}"
    if scope.edition is not None and source.edition is not None and source.edition != scope.edition:
        return f"a fonte pertence à edição {source.edition}, mas foi solicitada a edição {scope.edition}"
    return None


def path_matches_scope(path: str, scope: SelectionScope) -> bool:
    """Filtro barato da listagem; a leitura fará a validação completa."""
    assessment = assess_source(path)
    if not assessment.process:
        return True
    if scope.needs_clarification:
        return False
    if scope.process and assessment.process != scope.process:
        return False
    if scope.year and assessment.year != scope.year:
        return False
    if scope.edition is not None and assessment.edition is not None:
        return assessment.edition == scope.edition
    return True


def response_source_mismatches(text: str, scope: SelectionScope) -> tuple[str, ...]:
    """Encontra URLs versionadas incompatíveis antes de liberar a resposta."""
    mismatches: list[str] = []
    for url in _URL_RE.findall(text):
        cleaned = url.rstrip(".,;:)")
        assessment = assess_source(cleaned)
        if not assessment.process:
            continue
        if source_rejection_reason(scope, assessment):
            mismatches.append(cleaned)
    return tuple(dict.fromkeys(mismatches))


def scope_prompt(scope: SelectionScope) -> str:
    """Instrução redundante ao modelo; a autorização real continua no backend."""
    if not scope.must_filter:
        return ""
    if scope.needs_clarification:
        return (
            "## Filtro obrigatório de processo/edição\n\n"
            "A pergunta não identifica com segurança o processo e o ano. Peça ao usuário esses dois dados "
            "antes de responder fatos. O backend recusará fontes versionadas enquanto houver ambiguidade."
        )
    return (
        "## Filtro obrigatório de processo/edição\n\n"
        f"Esta conversa está filtrada para **{scope.label}**"
        + (f" (`{scope.slug}`)" if scope.slug else "")
        + ". Não use, compare nem cite fontes de outra edição."
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, stripped
    match = re.match(r"^---\s*\n(?P<head>.*?)\n---\s*(?:\n|$)", stripped, re.S)
    if not match:
        return {}, stripped
    metadata: dict[str, str] = {}
    for line in match.group("head").splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, stripped[match.end() :]


def _scopes_in_text(text: str) -> list[tuple[str, int, int | None]]:
    normalized = _normalize(text)
    found: list[tuple[str, int, int | None]] = []
    for match in _SLUG_RE.finditer(normalized):
        found.append(
            (
                _normalize_process(match.group("process")),
                2000 + int(match.group("year")),
                int(match.group("edition")),
            )
        )
    for pattern in (_PROCESS_YEAR_RE, _YEAR_PROCESS_RE):
        for match in pattern.finditer(normalized):
            process = _normalize_process(match.group("process"))
            year = int(match.group("year"))
            found.append((process, year, 1 if process == "sisu" else None))
    return list(dict.fromkeys(found))


def _same_scope(left: tuple[str, int, int | None], right: tuple[str, int, int | None]) -> bool:
    if left[0] != right[0] or left[1] != right[1]:
        return False
    return left[2] is None or right[2] is None or left[2] == right[2]


def _scope_label(scope: tuple[str, int, int | None]) -> str:
    return f"{scope[0].upper()} {scope[1]}" + (f" edição {scope[2]}" if scope[2] not in {None, 1} else "")


def _process_in_text(normalized: str) -> str | None:
    for alias in (
        "sisu",
        "prosel",
        "vestibular",
        "transferencia",
        "reingresso",
        "portador de diploma",
        "portador",
        "vagas residuais",
        "vagasresiduais",
    ):
        if re.search(rf"\b{alias}\b", normalized):
            return _normalize_process(alias)
    return None


def _normalize_process(process: str) -> str:
    normalized = _normalize(process)
    if normalized in {"vestibular", "prosel"}:
        return "prosel"
    if normalized == "portador de diploma":
        return "portador"
    if normalized == "vagas residuais":
        return "vagasresiduais"
    return normalized


def _has_selection_intent(normalized: str) -> bool:
    return _process_in_text(normalized) is not None or any(term in normalized for term in _SELECTION_INTENT_TERMS)


def _selection_year_in_text(normalized: str) -> int | None:
    """Evita confundir ano do ENEM, edital ou documento com a edição pedida."""
    for pattern in (_PROCESS_YEAR_RE, _YEAR_PROCESS_RE):
        match = pattern.search(normalized)
        if match:
            return int(match.group("year"))
    explicit = re.search(r"\b(?:edicao|processo(?: seletivo)?|sisu|prosel)\s+(?:de\s+)?(20\d{2})\b", normalized)
    if explicit:
        return int(explicit.group(1))
    short_follow_up = re.fullmatch(r"(?:e\s+|para\s+|de\s+)?(20\d{2})[?.!\s]*", normalized)
    if short_follow_up:
        return int(short_follow_up.group(1))
    return None


def _normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()
