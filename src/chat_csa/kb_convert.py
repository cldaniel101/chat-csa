"""Conversão de arquivos enviados em Markdown para a base de conhecimento.

Usado pelo POST /kb/upload: cada arquivo recebido vira um conceito OKF em
Markdown; o original não é preservado. A conversão roda dentro do request.

- PDF: texto extraído por layout, página a página, + uma imagem rasterizada
  por página (a imagem devolve a estrutura que o texto perde).
- Imagem: uma chamada multimodal.
- csv/tsv: tabela Markdown (mesmo render da leitura).
- md/txt/json: texto direto.
- Demais tipos: sem conversão nesta versão.

Fidelidade: o texto extraído é o esqueleto; o modelo multimodal só altera
onde a imagem mostra estrutura comprovadamente perdida (tabela, formulário,
coluna, figura) e nunca inventa conteúdo.
"""

from __future__ import annotations

import base64
import io
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# DPI da rasterização das páginas enviadas ao modelo multimodal.
DEFAULT_DPI = 150

# Tempo máximo de um extrator externo (pdftotext/pdftoppm), em segundos.
_EXTRACTOR_TIMEOUT_S = 120


class ConversionError(RuntimeError):
    """Falha de conversão de um arquivo (vira converted:false com motivo)."""


@dataclass(frozen=True)
class PdfPage:
    """Página do PDF: texto extraído (layout) + imagem renderizada (PNG)."""

    number: int  # 1-based
    text: str
    image: bytes | None


# ---------------------------------------------------------------------------
# PDF: texto por página (layout) + imagem por página
# ---------------------------------------------------------------------------


def extract_pdf_pages(content: bytes) -> list[PdfPage]:
    """Extrai texto (layout) e imagem de cada página, em memória e na ordem.

    O texto vem do `pdftotext -layout` quando disponível (as páginas saem
    separadas por form feed) e cai para o `pypdf`; a imagem vem do PyMuPDF e
    cai para o `pdftoppm`. Uma página pode ficar sem texto (PDF digitalizado)
    ou sem imagem (nenhum rasterizador) — nunca as duas fontes são exigidas.
    """
    texts = _extract_pdf_texts(content)
    images = _rasterize_pdf(content)
    count = max(len(texts), len(images))
    if count == 0:
        raise ConversionError("PDF sem páginas legíveis")
    return [
        PdfPage(
            number=index + 1,
            text=texts[index] if index < len(texts) else "",
            image=images[index] if index < len(images) else None,
        )
        for index in range(count)
    ]


def _extract_pdf_texts(content: bytes) -> list[str]:
    """Texto por página, na ordem; lista vazia se não houver texto."""
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-", "-"],
                input=content,
                capture_output=True,
                timeout=_EXTRACTOR_TIMEOUT_S,
            )
        except Exception:
            result = None
        if result is not None and result.returncode == 0:
            text = result.stdout.decode("utf-8", errors="replace")
            pages = text.split("\f")
            if pages and not pages[-1].strip():
                pages.pop()
            if any(page.strip() for page in pages):
                return [page.strip() for page in pages]

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ConversionError(f"texto do PDF: {exc}") from exc


def _rasterize_pdf(content: bytes) -> list[bytes]:
    """Uma imagem PNG por página, na ordem."""
    images = _rasterize_with_pymupdf(content)
    if images is not None:
        return images
    return _rasterize_with_pdftoppm(content)


def _rasterize_with_pymupdf(content: bytes) -> list[bytes] | None:
    """Rasteriza com PyMuPDF; None quando a biblioteca não está instalada."""
    try:
        try:
            import pymupdf  # PyMuPDF >= 1.24
        except ImportError:  # pragma: no cover - instalações antigas
            import fitz as pymupdf  # type: ignore[no-redef]
    except ImportError:
        return None
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ConversionError(f"imagem do PDF (PyMuPDF): {exc}") from exc
    try:
        return [page.get_pixmap(dpi=DEFAULT_DPI).tobytes("png") for page in document]
    finally:
        document.close()


def _rasterize_with_pdftoppm(content: bytes) -> list[bytes]:
    """Rasteriza com o poppler (Docker/local); lista vazia sem ele."""
    if not shutil.which("pdftoppm"):
        return []
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "entrada.pdf"
        pdf_path.write_bytes(content)
        prefix = Path(tmp) / "pagina"
        try:
            result = subprocess.run(
                ["pdftoppm", "-png", "-r", str(DEFAULT_DPI), str(pdf_path), str(prefix)],
                capture_output=True,
                timeout=_EXTRACTOR_TIMEOUT_S * 3,
            )
        except Exception as exc:
            raise ConversionError(f"imagem do PDF (pdftoppm): {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ConversionError(f"imagem do PDF (pdftoppm): {detail[:200]}")
        return [path.read_bytes() for path in _sorted_pages(Path(tmp))]


def _sorted_pages(directory: Path) -> list[Path]:
    """Ordena `pagina-1.png`, `pagina-2.png`, …, `pagina-10.png` por número."""

    def page_number(path: Path) -> int:
        try:
            return int(path.stem.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    return sorted(directory.glob("pagina-*.png"), key=page_number)


# ---------------------------------------------------------------------------
# Modelo multimodal: chamadas em lotes de páginas
# ---------------------------------------------------------------------------

# Quantas páginas entram em cada chamada multimodal (D3).
DEFAULT_PAGES_PER_CALL = 4

# Uma chamada multimodal: (prompt, imagens PNG) -> Markdown.
ModelCall = Callable[[str, list[bytes]], str]

_FAITHFULNESS_RULES = (
    "Você transcreve documentos para Markdown, com fidelidade ao original.\n"
    "- Nunca invente conteúdo que não está no documento.\n"
    "- Preserve títulos, listas, ênfases, links e tabelas em Markdown.\n"
    "- Devolva somente o Markdown, sem comentários nem cercas de código."
)

# Esqueleto do PDF: o texto extraído manda; a imagem devolve a estrutura perdida.
_PDF_SKELETON_RULES = (
    "- O texto extraído abaixo é o esqueleto: mantenha tudo o que ele traz.\n"
    "- Compare cada página com a imagem e corrija APENAS onde a estrutura se "
    "perdeu no texto (tabelas, formulários, colunas, figuras, ordem de leitura)."
)


def convert_pdf_pages(
    pages: Sequence[PdfPage],
    call: ModelCall,
    *,
    pages_per_call: int = DEFAULT_PAGES_PER_CALL,
) -> str:
    """Converte as páginas em Markdown, um lote de páginas por chamada.

    Os trechos voltam na ordem das páginas; uma página em branco pode gerar
    trecho vazio, mas um documento inteiro sem Markdown é falha.
    """
    if pages_per_call < 1:
        raise ValueError("pages_per_call deve ser >= 1")
    chunks: list[str] = []
    for batch in _page_batches(pages, pages_per_call):
        markdown = call(_batch_prompt(batch), [page.image for page in batch if page.image])
        chunks.append(markdown.strip())
    result = "\n\n".join(chunk for chunk in chunks if chunk)
    if not result:
        raise ConversionError("conversão vazia (o modelo não devolveu Markdown)")
    return result


def _page_batches(pages: Sequence[PdfPage], size: int) -> list[Sequence[PdfPage]]:
    return [pages[start : start + size] for start in range(0, len(pages), size)]


def convert_image(content: bytes, call: ModelCall) -> str:
    """Converte um arquivo de imagem em Markdown pela chamada multimodal."""
    markdown = call(_image_prompt(), [content]).strip()
    if not markdown:
        raise ConversionError("conversão vazia (o modelo não devolveu Markdown)")
    return markdown


def _image_prompt() -> str:
    return "\n".join(
        [
            _FAITHFULNESS_RULES,
            "",
            "Não há texto extraído: a imagem anexada é o documento a transcrever.",
            "Converta a imagem em Markdown, na ordem de leitura.",
        ]
    )


def _batch_prompt(batch: Sequence[PdfPage]) -> str:
    """Prompt do lote: regras de fidelidade + texto extraído de cada página."""
    first, last = batch[0].number, batch[-1].number
    image_pages = [page.number for page in batch if page.image]
    lines = [_FAITHFULNESS_RULES, _PDF_SKELETON_RULES, ""]
    if image_pages:
        lines.append(
            "As imagens anexadas, na ordem, são as páginas "
            + ", ".join(str(number) for number in image_pages)
            + "."
        )
    lines.append(f"Converta as páginas {first} a {last} em Markdown, na ordem.")
    for page in batch:
        text = page.text.strip()
        if text:
            lines += ["", f"Página {page.number} — texto extraído:", '"""', text, '"""']
        else:
            lines += ["", f"Página {page.number} — sem texto extraído (use a imagem)."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tipos determinísticos: csv/tsv (tabela) e texto direto
# ---------------------------------------------------------------------------


def convert_table(path: str, content: bytes) -> str:
    """Converte csv/tsv em tabela Markdown (mesmo render da leitura)."""
    from .kb import render_bytes  # import tardio: evita ciclo com kb.py

    table = render_bytes(path, content).strip()
    if not table or table.startswith("(tabela vazia"):
        raise ConversionError("tabela vazia")
    return table


def convert_text(path: str, content: bytes) -> str:
    """Md/txt/json: texto direto; o frontmatter antigo sai (o OKF é reescrito)."""
    text = _decode_utf8(content)
    if text is None:
        raise ConversionError("arquivo não é texto UTF-8")
    body = _strip_frontmatter(text).strip()
    if not body:
        raise ConversionError("texto vazio")
    return body


_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Remove um bloco YAML inicial (`--- ... ---`) do texto."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def _decode_utf8(content: bytes) -> str | None:
    """Decodifica UTF-8; None para bytes que parecem binários."""
    if b"\x00" in content[:4096]:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------------------
# Despacho por tipo: converte o arquivo inteiro ou devolve o motivo
# ---------------------------------------------------------------------------

_PDF_SUFFIXES = {".pdf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_TABLE_SUFFIXES = {".csv", ".tsv"}
_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json"}


@dataclass(frozen=True)
class ConversionResult:
    """Markdown convertido OU o motivo da falha (nunca os dois)."""

    markdown: str | None = None
    error: str | None = None

    @property
    def converted(self) -> bool:
        return self.markdown is not None


def conversion_kind(path: str) -> str | None:
    """Tipo de conversão do caminho: pdf | image | table | text | None."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _PDF_SUFFIXES:
        return "pdf"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _TABLE_SUFFIXES:
        return "table"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    return None


def convert_file(
    path: str,
    content: bytes,
    call: ModelCall,
    *,
    pages_per_call: int = DEFAULT_PAGES_PER_CALL,
) -> ConversionResult:
    """Converte um arquivo; nunca levanta — a falha vira motivo no resultado.

    É o contrato que mantém o lote vivo: um arquivo que não converte não
    impede a conversão dos demais.
    """
    try:
        markdown = _convert(path, content, call, pages_per_call=pages_per_call)
    except ConversionError as exc:
        return ConversionResult(error=str(exc))
    except Exception as exc:  # erro inesperado do extrator/modelo
        return ConversionResult(error=f"falha inesperada na conversão: {exc}")
    return ConversionResult(markdown=markdown)


def _convert(path: str, content: bytes, call: ModelCall, *, pages_per_call: int) -> str:
    kind = conversion_kind(path)
    if kind == "pdf":
        return convert_pdf_pages(extract_pdf_pages(content), call, pages_per_call=pages_per_call)
    if kind == "image":
        return convert_image(content, call)
    if kind == "table":
        return convert_table(path, content)
    if kind == "text":
        return convert_text(path, content)
    suffix = PurePosixPath(path).suffix.lower() or path
    raise ConversionError(f"tipo sem conversão nesta versão: {suffix}")


# ---------------------------------------------------------------------------
# Chamada multimodal real (LLM do serviço)
# ---------------------------------------------------------------------------


def default_model_call() -> ModelCall:
    """Chamada multimodal real: LLM do serviço (get_llm) com visão.

    `KB_CONVERT_MODEL` sobrescreve o modelo apenas para a conversão do upload;
    sem ele, vale o modelo configurado do serviço (`LLM_MODEL`).
    """
    from langchain_core.messages import HumanMessage

    from .agent.factory import get_llm

    model = (os.getenv("KB_CONVERT_MODEL") or "").strip() or None
    llm = get_llm(model=model, temperature=0.1)

    def call(prompt: str, images: list[bytes]) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image in images:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{_image_mime(image)};base64,{encoded}"},
                }
            )
        response = llm.invoke([HumanMessage(content=content)])
        return _response_text(response.content)

    return call


def _image_mime(image: bytes) -> str:
    """Content-type da imagem pelo magic number (PDF renderiza em PNG)."""
    if image.startswith(b"\x89PNG"):
        return "image/png"
    if image.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image.startswith(b"GIF8"):
        return "image/gif"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _response_text(content: object) -> str:
    """Texto da resposta do modelo (string ou blocos de conteúdo)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)