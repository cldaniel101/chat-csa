"""FAQ curada em Markdown, usada como referência para o agente.

O módulo lê arquivos Markdown versionados (FAQ) e recupera as entradas mais
parecidas com a pergunta do usuário. As entradas não são respostas diretas:
elas são injetadas no prompt do agente como referência curada, e a resposta é
formulada pelo agente no turno — adaptada ao contexto da conversa e com
citação das fontes. Entradas marcadas como `dynamic` avisam que a informação
pode mudar e devem ser conferidas nas fontes oficiais.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_QA_CACHE_PATHS = (Path("docs/faq"), Path("knowledge/perguntas-frequentes"))
DEFAULT_MIN_MATCH_SCORE = 0.68

_FAQ_HEADER_RE = re.compile(r"^##\s+(FAQ-[A-Za-z0-9_-]+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
_QUESTION_HEADER_RE = re.compile(r"^###\s+(?:\d+\.\s*)?(.+\?)\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\*\*(?P<name>[^*]+):\*\*\s*(?P<value>.*?)\s*$")
_URL_RE = re.compile(r"https?://\S+")

_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "ate",
    "com",
    "como",
    "da",
    "das",
    "de",
    "devo",
    "do",
    "dos",
    "e",
    "em",
    "eu",
    "faco",
    "faz",
    "fazer",
    "me",
    "minha",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelo",
    "posso",
    "pra",
    "que",
    "qual",
    "quando",
    "quais",
    "se",
    "tem",
    "tenho",
    "uefs",
    "um",
    "uma",
}


@dataclass(frozen=True)
class QACacheEntry:
    """Entrada de FAQ carregada de Markdown."""

    entry_id: str
    question: str
    answer: str
    source_label: str
    source_url: str
    cache_policy: str
    path: Path
    alternatives: tuple[str, ...] = ()
    category: str = ""
    last_verified: str = ""


@dataclass(frozen=True)
class QACacheHit:
    """Resultado de uma correspondência do cache."""

    entry: QACacheEntry
    score: float
    matched_question: str

    def to_markdown(self) -> str:
        answer = self.entry.answer.strip()
        if not answer.endswith((".", "!", "?", ":", ";")):
            answer += "."

        verified = f"; verificado {self.entry.last_verified}" if self.entry.last_verified else ""
        source = self.entry.source_label or "FAQ curada"
        url = self.entry.source_url or "fonte Markdown local"
        return (
            f"{answer} [1]\n\n"
            "Fontes:\n"
            f"[1] {source} — {url} (cache {self.entry.entry_id}{verified})"
        )


def get_cache_paths() -> list[Path]:
    """Retorna os caminhos configurados para cache de FAQ."""
    raw = os.getenv("CHAT_CSA_QA_CACHE_PATHS", "").strip()
    if raw:
        return [Path(part.strip()) for part in raw.split(os.pathsep) if part.strip()]
    return list(DEFAULT_QA_CACHE_PATHS)


def lookup_cached_matches(
    question: str, paths: list[Path] | None = None, top_k: int = 3
) -> list[QACacheHit]:
    """Recupera as entradas FAQ mais parecidas com a pergunta, para usar como contexto.

    Não filtra por política de cache: entradas `dynamic` entram marcadas para
    conferência nas fontes oficiais. O resultado alimenta o prompt do agente —
    a resposta final é formulada pelo LLM no turno, não copiada do Markdown.
    """
    if os.getenv("CHAT_CSA_QA_CACHE_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
        return []

    query = question.strip()
    if not query:
        return []

    hits = [
        QACacheHit(entry=entry, score=score, matched_question=matched)
        for entry in load_cache_entries(paths)
        for score, matched in [_score_entry(query, entry)]
    ]
    hits.sort(key=lambda hit: hit.score, reverse=True)
    threshold = _min_match_score()
    return [hit for hit in hits if hit.score >= threshold][:top_k]


def lookup_cached_answer(question: str, paths: list[Path] | None = None) -> QACacheHit | None:
    """Procura uma entrada estática suficientemente parecida com a pergunta.

    Mantido para compatibilidade com testes anteriores; o servidor usa
    `lookup_cached_matches` para injetar contexto no agente.
    """
    for hit in lookup_cached_matches(question, paths=paths, top_k=1):
        if hit.entry.cache_policy == "static":
            return hit
    return None


def format_faq_reference(entry: QACacheEntry) -> str:
    """Formata uma entrada como bloco de referência curada para o prompt do agente.

    O agente adapta o conteúdo ao contexto da conversa e cita a fonte. Entradas
    `dynamic` ganham aviso de que a informação pode ter mudado.
    """
    policy_note = (
        ""
        if entry.cache_policy == "static"
        else " (pode ter mudado — confira nas fontes oficiais antes de afirmar datas, prazos ou situação atual)"
    )
    verified = f" (verificado em {entry.last_verified})" if entry.last_verified else ""
    answer = entry.answer.strip()
    if not answer.endswith((".", "!", "?", ":", ";")):
        answer += "."
    source = entry.source_label or "FAQ curada"
    url = entry.source_url or "fonte Markdown local"
    return (
        f"### {entry.entry_id}{verified} — {entry.question}{policy_note}\n\n"
        f"{answer}\n\n"
        f"Fonte: {source} — {url}"
    )


def load_cache_entries(paths: list[Path] | None = None) -> list[QACacheEntry]:
    """Carrega entradas FAQ dos arquivos Markdown informados."""
    entries: list[QACacheEntry] = []
    selected_paths = get_cache_paths() if paths is None else paths
    for path in _iter_markdown_files(selected_paths):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        metadata, body = _split_frontmatter(text)
        entries.extend(_parse_structured_faq(path, metadata, body))
        entries.extend(_parse_simple_faq(path, metadata, body))
    return entries


def _iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*.md")) if p.name.lower() != "index.md")
    return files


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text

    end = re.search(r"\n---\s*\n", text[3:])
    if end is None:
        return {}, text

    frontmatter = text[3 : end.start() + 3]
    body = text[end.end() + 3 :]
    metadata: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, body


def _parse_structured_faq(path: Path, metadata: dict[str, str], body: str) -> list[QACacheEntry]:
    matches = list(_FAQ_HEADER_RE.finditer(body))
    entries: list[QACacheEntry] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[start:end]
        entry_id = match.group(1).strip()
        question = match.group(2).strip()
        answer = _field_block(section, "Resposta")
        if not answer:
            continue
        source_label = _field_line(section, "Fonte") or metadata.get("title", "")
        entries.append(
            QACacheEntry(
                entry_id=entry_id,
                question=question,
                answer=answer,
                source_label=source_label,
                source_url=_source_url_for(source_label, metadata, body),
                cache_policy=(_field_line(section, "Cache") or metadata.get("cache") or "static").lower(),
                path=path,
                alternatives=tuple(_list_after_field(section, "Perguntas equivalentes")),
                category=_field_line(section, "Categoria"),
                last_verified=metadata.get("last_verified", metadata.get("timestamp", "")),
            )
        )
    return entries


def _parse_simple_faq(path: Path, metadata: dict[str, str], body: str) -> list[QACacheEntry]:
    if _FAQ_HEADER_RE.search(body):
        return []

    matches = list(_QUESTION_HEADER_RE.finditer(body))
    entries: list[QACacheEntry] = []
    for index, match in enumerate(matches, start=1):
        start = match.end()
        end = matches[index].start() if index < len(matches) else len(body)
        section = body[start:end]
        answer = _trim_simple_answer(section)
        if not answer:
            continue
        entries.append(
            QACacheEntry(
                entry_id=f"{path.stem}-{index:03d}",
                question=match.group(1).strip(),
                answer=answer,
                source_label=metadata.get("title", path.stem),
                source_url=metadata.get("resource", ""),
                cache_policy=metadata.get("cache", "static").lower(),
                path=path,
                last_verified=metadata.get("timestamp", ""),
            )
        )
    return entries


def _field_line(section: str, field_name: str) -> str:
    wanted = _normalize_field_name(field_name)
    for line in section.splitlines():
        match = _FIELD_RE.match(line.strip())
        if match and _normalize_field_name(match.group("name")) == wanted:
            return match.group("value").strip()
    return ""


def _field_block(section: str, field_name: str) -> str:
    wanted = _normalize_field_name(field_name)
    lines = section.splitlines()
    out: list[str] = []
    active = False
    for line in lines:
        match = _FIELD_RE.match(line.strip())
        if match:
            if active:
                break
            if _normalize_field_name(match.group("name")) == wanted:
                active = True
                if match.group("value").strip():
                    out.append(match.group("value").strip())
            continue
        if active:
            out.append(line.rstrip())
    return "\n".join(out).strip()


def _list_after_field(section: str, field_name: str) -> list[str]:
    block = _field_block(section, field_name)
    items: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def _trim_simple_answer(section: str) -> str:
    lines: list[str] = []
    for line in section.splitlines():
        if line.startswith("## "):
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _source_url_for(source_label: str, metadata: dict[str, str], body: str) -> str:
    if metadata.get("resource"):
        return metadata["resource"]

    urls = [url.rstrip(".,)") for url in _URL_RE.findall(body)]
    if not urls:
        return ""

    source = _normalize(source_label)
    if "edital" in source:
        edital = next((url for url in urls if "edital" in _normalize(url)), "")
        if edital:
            return edital
    if any(term in source for term in ("anexo", "document", "download", "modelo")):
        downloads = next((url for url in urls if "download" in _normalize(url)), "")
        if downloads:
            return downloads
    if "sidoc" in source:
        sidoc = next((url for url in urls if "sidoc" in _normalize(url)), "")
        if sidoc:
            return sidoc
    if "heteroidentificacao" in source:
        hetero = next((url for url in urls if "heteroidentificacao" in _normalize(url)), "")
        if hetero:
            return hetero
    return urls[0]


def _score_entry(query: str, entry: QACacheEntry) -> tuple[float, str]:
    candidates = (entry.question, *entry.alternatives)
    scored = [(_score_question(query, candidate), candidate) for candidate in candidates]
    return max(scored, key=lambda item: item[0])


def _score_question(query: str, candidate: str) -> float:
    query_norm = _normalize(query)
    candidate_norm = _normalize(candidate)
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return 0.92

    query_tokens = set(_tokens(query_norm))
    candidate_tokens = set(_tokens(candidate_norm))
    if not query_tokens or not candidate_tokens:
        lexical = 0.0
    else:
        overlap = len(query_tokens & candidate_tokens)
        lexical = max(overlap / len(query_tokens), overlap / len(candidate_tokens))

    fuzzy = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    return max(lexical, fuzzy)


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text) if token not in _STOPWORDS and len(token) > 1]


def _normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _normalize_field_name(text: str) -> str:
    return _normalize(text).strip(":")


def _min_match_score() -> float:
    try:
        return float(os.getenv("CHAT_CSA_QA_CACHE_MIN_SCORE", str(DEFAULT_MIN_MATCH_SCORE)))
    except ValueError:
        return DEFAULT_MIN_MATCH_SCORE
