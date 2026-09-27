"""Processamento do POST /kb/upload: converte o lote em conceitos OKF.

Fluxo (tudo dentro do request, antes do commit):

1. valida os caminhos declarados (relativos, únicos, com pasta) e o orçamento;
2. converte cada arquivo em Markdown (kb_convert) — falha não aborta o lote;
3. monta o conceito OKF (kb_okf), com citação opcional declarada;
4. atualiza o índice da seção e o índice raiz;
5. grava conceitos + índices num único commit atômico.

O arquivo original não é preservado — só o conceito `.md`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from .kb import KBNotFoundError, KnowledgeBase
from .kb_convert import (
    DEFAULT_PAGES_PER_CALL,
    ModelCall,
    conversion_kind,
    convert_file,
)
from .kb_okf import (
    OKF_CONTENT_TEMPLATE,
    InvalidPathError,
    build_concept,
    concept_metadata,
    normalize_declared_path,
    section_of,
    update_root_index,
    update_section_index,
)

# Orçamento do corpo do request na runtime serverless (~4.5 MB).
DEFAULT_MAX_UPLOAD_BYTES = 4_500_000
ROOT_INDEX_PATH = "index.md"


@dataclass(frozen=True)
class FileResult:
    """Resultado por arquivo do upload (contrato aditivo da resposta)."""

    path: str
    ok: bool
    size: int
    converted: bool
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "path": self.path,
            "ok": self.ok,
            "size": self.size,
            "converted": self.converted,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass(frozen=True)
class BatchResult:
    """Resultado do lote: sha do commit (ou None) + um resultado por arquivo."""

    sha: str | None
    files: list[FileResult]


@dataclass(frozen=True)
class _Concept:
    """Conceito pronto para o commit (caminho, conteúdo e itens de índice)."""

    path: str
    content: str
    title: str
    description: str
    section: str


def process_upload(
    kb: KnowledgeBase,
    payload: Sequence[tuple[str, bytes]],
    *,
    model_call: ModelCall,
    sources: Mapping[str, str] | None = None,
    message: str = "",
    pages_per_call: int = DEFAULT_PAGES_PER_CALL,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> BatchResult:
    """Converte e commita o lote; devolve o resultado por arquivo e o sha."""
    results: list[FileResult | None] = [None] * len(payload)
    accepted: list[tuple[int, str, str, bytes]] = []  # índice, declarado, conceito, bytes
    seen: set[str] = set()

    for index, (path, content) in enumerate(payload):
        size = len(content)
        try:
            concept_path = normalize_declared_path(path)
        except InvalidPathError as exc:
            results[index] = FileResult(
                path, ok=False, size=size, converted=False, error=f"caminho inválido: {exc}"
            )
            continue
        if concept_path in seen:
            results[index] = FileResult(
                path, ok=False, size=size, converted=False, error="caminho duplicado no lote"
            )
            continue
        seen.add(concept_path)
        if size > max_bytes:
            results[index] = FileResult(
                path,
                ok=True,
                size=size,
                converted=False,
                error=f"acima do orçamento do request ({size} bytes)",
            )
            continue
        if conversion_kind(path) is None:
            suffix = PurePosixPath(path).suffix.lower() or path
            results[index] = FileResult(
                path,
                ok=True,
                size=size,
                converted=False,
                error=f"tipo sem conversão nesta versão: {suffix}",
            )
            continue
        accepted.append((index, path, concept_path, content))

    template_text = _read_text(kb, OKF_CONTENT_TEMPLATE)
    concepts: list[_Concept] = []
    for index, declared, concept_path, content in accepted:
        conversion = convert_file(declared, content, model_call, pages_per_call=pages_per_call)
        if not conversion.converted:
            results[index] = FileResult(
                declared,
                ok=True,
                size=len(content),
                converted=False,
                error=conversion.error,
            )
            continue
        markdown = conversion.markdown or ""
        concept = build_concept(
            markdown,
            path=declared,
            source=_declared_source(sources, declared, concept_path),
            template_text=template_text,
        )
        title, description = concept_metadata(markdown, declared)
        concepts.append(
            _Concept(
                path=concept_path,
                content=concept,
                title=title,
                description=description,
                section=section_of(concept_path),
            )
        )
        results[index] = FileResult(declared, ok=True, size=len(content), converted=True)

    items = _commit_items(kb, concepts)
    sha: str | None = None
    if items:
        commit_message = message.strip() or f"kb: upload de {len(payload)} arquivo(s) via /kb/upload"
        commit = kb.write(items, commit_message)
        sha = commit.sha or None
    return BatchResult(sha=sha, files=[result for result in results if result is not None])


def _declared_source(
    sources: Mapping[str, str] | None, declared: str, concept_path: str
) -> str | None:
    """Fonte declarada pelo remetente (caminho declarado ou já normalizado)."""
    if not sources:
        return None
    source = sources.get(declared) or sources.get(concept_path)
    return source.strip() if isinstance(source, str) and source.strip() else None


def _read_text(kb: KnowledgeBase, path: str) -> str | None:
    """Texto de um arquivo da base; None quando ele não existe."""
    try:
        return kb.read(path).content.decode("utf-8", errors="replace")
    except KBNotFoundError:
        return None


def _commit_items(kb: KnowledgeBase, concepts: list[_Concept]) -> list[tuple[str, str]]:
    """Conceitos + índices (seção e raiz) do lote, para um único commit."""
    if not concepts:
        return []
    items: list[tuple[str, str]] = [(concept.path, concept.content) for concept in concepts]
    existing_paths = kb.list("")

    sections: dict[str, list[_Concept]] = {}
    for concept in concepts:
        sections.setdefault(concept.section, []).append(concept)

    for section, section_concepts in sections.items():
        section_index_path = f"{section}/index.md"
        existing = _read_text(kb, section_index_path)
        if existing is not None:
            for concept in section_concepts:
                existing = update_section_index(
                    existing,
                    section=section,
                    title=concept.title,
                    concept_path=concept.path,
                    description=concept.description,
                )
            items.append((section_index_path, existing))
        elif not _section_exists(existing_paths, section):
            created: str | None = None
            for concept in section_concepts:
                created = update_section_index(
                    created,
                    section=section,
                    title=concept.title,
                    concept_path=concept.path,
                    description=concept.description,
                )
            items.append((section_index_path, created))

    root = _read_text(kb, ROOT_INDEX_PATH) or ""
    updated_root = root
    for concept in concepts:
        updated_root = update_root_index(
            updated_root,
            section=concept.section,
            title=concept.title,
            concept_path=concept.path,
            description=concept.description,
        )
    if updated_root != root:
        items.append((ROOT_INDEX_PATH, updated_root))
    return items


def _section_exists(existing_paths: list[str], section: str) -> bool:
    """True quando já existe algum arquivo na pasta da seção."""
    prefix = f"{section}/"
    return any(path.startswith(prefix) for path in existing_paths)