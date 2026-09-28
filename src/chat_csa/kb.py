"""Cliente da base de conhecimento remota.

A base vive num branch do próprio repositório (padrão: `data`, órfão) e é
lida em runtime pela API do GitHub. Em dev/testes, o backend `local` opera
sobre `KB_LOCAL_PATH`.

Interface única — usada em processo pelas tools do agente e pelo qa_cache;
os endpoints `/kb/*` também a usam, atrás da auth admin:

    kb = get_kb()
    kb.list(prefix="")                      # caminhos relativos à raiz da base
    kb.read("perguntas-frequentes/faq.md")  # KBFile (bytes + content_type)
    kb.write({"arquivo.md": b"..."}, "mensagem do commit")  # KBCommit

Regras de ouro:
- O agente usa somente `list`/`read` (KB_TOKEN, leitura). `write()` exige
  token de escrita e nunca é exposto ao agente.
- A conversão bytes→texto acontece só na leitura (`render_file`), nunca é
  gravada no branch.
- Sem escrita em disco no deploy: o backend github não persiste nada local;
  o cache TTL vive na memória da instância.
"""

from __future__ import annotations

import base64
import csv
import io
import mimetypes
import os
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

GITHUB_API = "https://api.github.com"
DEFAULT_BRANCH = "data"
DEFAULT_CACHE_TTL_S = 60.0
DEFAULT_LOCAL_PATH = Path("knowledge")
DEFAULT_CONTENT_TYPE = "application/octet-stream"

_CONTENT_TYPE_OVERRIDES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".pdf": "application/pdf",
}

_TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t"}


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------


class KBError(RuntimeError):
    """Erro base do cliente da base de conhecimento."""


class KBConfigError(KBError):
    """Configuração ausente ou inválida (KB_*)."""


class KBNotFoundError(KBError):
    """Arquivo, diretório ou branch da base não encontrado."""


class KBAuthError(KBError):
    """Credencial recusada pelo backend."""


class KBUpstreamError(KBError):
    """Falha de rede/API ao falar com o backend."""


# ---------------------------------------------------------------------------
# Configuração (por ambiente)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KBSettings:
    """Configuração do cliente, derivada das variáveis KB_*."""

    backend: str = "github"
    repo: str = ""
    branch: str = DEFAULT_BRANCH
    root: str = ""
    token: str = ""
    write_token: str = ""
    cache_ttl: float = DEFAULT_CACHE_TTL_S
    local_path: Path = DEFAULT_LOCAL_PATH

    @classmethod
    def from_env(cls) -> KBSettings:
        backend = (os.getenv("KB_BACKEND") or "github").strip().lower()
        if backend not in {"github", "local"}:
            raise KBConfigError(f"KB_BACKEND inválido: {backend!r} (esperado github|local)")
        token = (os.getenv("KB_TOKEN") or "").strip()
        return cls(
            backend=backend,
            repo=(os.getenv("KB_REPO") or "").strip(),
            branch=(os.getenv("KB_BRANCH") or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH,
            root=_normalize_root(os.getenv("KB_ROOT") or ""),
            token=token,
            write_token=(os.getenv("KB_WRITE_TOKEN") or "").strip() or token,
            cache_ttl=_parse_ttl(os.getenv("KB_CACHE_TTL")),
            local_path=Path(os.getenv("KB_LOCAL_PATH") or DEFAULT_LOCAL_PATH),
        )


def _parse_ttl(raw: str | None) -> float:
    if raw is None or not raw.strip():
        return DEFAULT_CACHE_TTL_S
    try:
        value = float(raw)
    except ValueError as exc:
        raise KBConfigError(f"KB_CACHE_TTL inválido: {raw!r} (esperado segundos)") from exc
    if value < 0:
        raise KBConfigError(f"KB_CACHE_TTL inválido: {raw!r} (não pode ser negativo)")
    return value


def _normalize_root(root: str) -> str:
    cleaned = root.strip().strip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise KBConfigError(f"KB_ROOT inválido: {root!r}")
    return "/".join(parts)


def _normalize_path(path: str) -> str:
    """Normaliza um caminho relativo à raiz da base e bloqueia `..`."""
    raw = (path or "").strip().replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise KBError(f"Caminho inválido: {path!r}")
    return "/".join(parts)


def _join_root(rel: str, root: str) -> str:
    return f"{root}/{rel}" if root else rel


def _strip_root(path: str, root: str) -> str | None:
    """Converte um caminho do branch em caminho relativo à raiz da base."""
    if not root:
        return path
    if path == root:
        return None
    prefix = root + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return None


def _content_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _CONTENT_TYPE_OVERRIDES:
        return _CONTENT_TYPE_OVERRIDES[suffix]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or DEFAULT_CONTENT_TYPE


# ---------------------------------------------------------------------------
# Tipos de retorno
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KBFile:
    """Arquivo da base: bytes originais + content-type inferido."""

    path: str
    content: bytes
    content_type: str = DEFAULT_CONTENT_TYPE

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class KBCommit:
    """Resultado de um write em lote (sha vazio no backend local)."""

    sha: str
    paths: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _Backend:
    """Contrato interno dos backends (github | local)."""

    def list(self, prefix: str) -> list[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self, path: str) -> KBFile:  # pragma: no cover - interface
        raise NotImplementedError

    def write(self, files: list[tuple[str, bytes]], message: str) -> KBCommit:  # pragma: no cover
        raise NotImplementedError

    def delete(self, path: str, message: str) -> KBCommit:  # pragma: no cover - interface
        raise NotImplementedError


class _GithubBackend(_Backend):
    """Backend de produção: GitHub Contents API + Git Data API.

    - list: árvore do branch de uma vez (`git/trees?recursive=1`), filtrando
      pelo prefixo; árvores truncadas caem num walk paginado da Contents API.
    - read: arquivo em texto/base64 (>1MB via download_url).
    - write: blobs + tree + commit + ref num único commit atômico por lote.
    """

    def __init__(self, settings: KBSettings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.repo:
            raise KBConfigError("KB_REPO não configurado (ex.: owner/repo).")
        self._settings = settings
        self._client = httpx.Client(
            base_url=GITHUB_API,
            timeout=30.0,
            transport=transport,
        )

    # -- helpers -----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def _headers(self, token: str) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "chat-csa-kb/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, url: str, *, token: str = "", **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, url, headers=self._headers(token), **kwargs)
        except httpx.HTTPError as exc:
            raise KBUpstreamError(f"Falha de rede ao chamar a API do GitHub: {exc}") from exc

    @staticmethod
    def _check(resp: httpx.Response, action: str) -> None:
        if resp.status_code in (401, 403):
            raise KBAuthError(
                f"GitHub recusou {action} ({resp.status_code}). "
                "Verifique KB_TOKEN/KB_WRITE_TOKEN e os escopos do token."
            )
        if resp.status_code == 404:
            raise KBNotFoundError(f"Não encontrado: {action} (404).")
        if resp.status_code >= 400:
            raise KBUpstreamError(f"GitHub falhou em {action} ({resp.status_code}): {resp.text[:300]}")

    def _ref_commit_sha(self, token: str) -> str:
        repo, branch = self._settings.repo, self._settings.branch
        resp = self._request("GET", f"/repos/{repo}/git/ref/heads/{branch}", token=token)
        if resp.status_code == 404:
            raise KBNotFoundError(f"Branch da base não encontrado: {branch!r}.")
        self._check(resp, f"ler o branch {branch!r}")
        return resp.json()["object"]["sha"]

    # -- list ---------------------------------------------------------------

    def list(self, prefix: str) -> list[str]:
        repo, branch, root = self._settings.repo, self._settings.branch, self._settings.root
        token = self._settings.token
        commit_sha = self._ref_commit_sha(token)
        resp = self._request(
            "GET",
            f"/repos/{repo}/git/trees/{commit_sha}",
            token=token,
            params={"recursive": "1"},
        )
        self._check(resp, f"listar a árvore de {branch!r}")
        payload = resp.json()
        if payload.get("truncated"):
            # Base grande demais para a árvore recursiva: walk paginado.
            return self._list_via_contents(prefix, token)
        paths: list[str] = []
        for item in payload.get("tree", []):
            if item.get("type") != "blob":
                continue
            rel = _strip_root(item.get("path", ""), root)
            if rel is None:
                continue
            if prefix and not rel.startswith(prefix):
                continue
            paths.append(rel)
        return sorted(paths)

    def _list_via_contents(self, prefix: str, token: str) -> list[str]:
        """Fallback paginado da Contents API para árvores truncadas."""
        repo, branch, root = self._settings.repo, self._settings.branch, self._settings.root
        start = root or ""
        pending = [start]
        paths: list[str] = []
        while pending:
            directory = pending.pop()
            page = 1
            while True:
                resp = self._request(
                    "GET",
                    f"/repos/{repo}/contents/{quote(directory, safe='/')}",
                    token=token,
                    params={"ref": branch, "per_page": 100, "page": page},
                )
                self._check(resp, f"listar {directory or '/'} em {branch!r}")
                items = resp.json()
                if not isinstance(items, list):
                    break
                for item in items:
                    if item.get("type") == "dir":
                        pending.append(item["path"])
                        continue
                    rel = _strip_root(item.get("path", ""), root)
                    if rel is None:
                        continue
                    if prefix and not rel.startswith(prefix):
                        continue
                    paths.append(rel)
                if len(items) < 100:
                    break
                page += 1
        return sorted(paths)

    # -- read ---------------------------------------------------------------

    def read(self, path: str) -> KBFile:
        repo, branch, root = self._settings.repo, self._settings.branch, self._settings.root
        token = self._settings.token
        full = _join_root(path, root)
        resp = self._request(
            "GET",
            f"/repos/{repo}/contents/{quote(full, safe='/')}",
            token=token,
            params={"ref": branch},
        )
        if resp.status_code == 404:
            raise KBNotFoundError(f"Arquivo não encontrado na base: {path!r}.")
        self._check(resp, f"ler {full!r}")
        payload = resp.json()
        if isinstance(payload, list):
            raise KBError(f"{path!r} é um diretório; use list().")
        content_b64 = payload.get("content") or ""
        if payload.get("encoding") == "base64" and content_b64:
            content = base64.b64decode(content_b64)
        else:
            # Arquivos grandes (>1MB) vêm sem `content`: baixa o original.
            download_url = payload.get("download_url")
            if not download_url:
                raise KBUpstreamError(f"GitHub não retornou conteúdo nem download_url para {full!r}.")
            raw = self._request("GET", download_url, token=token)
            self._check(raw, f"baixar {full!r}")
            content = raw.content
        return KBFile(path=path, content=content, content_type=_content_type(path))

    # -- write --------------------------------------------------------------

    def write(self, files: list[tuple[str, bytes]], message: str) -> KBCommit:
        repo, branch, root = self._settings.repo, self._settings.branch, self._settings.root
        token = self._settings.write_token
        if not token:
            raise KBConfigError(
                "KB_WRITE_TOKEN (ou KB_TOKEN com escopo de escrita) não configurado; "
                "a base é somente leitura."
            )
        base_commit = self._ref_commit_sha(token)
        commit_resp = self._request("GET", f"/repos/{repo}/git/commits/{base_commit}", token=token)
        self._check(commit_resp, "ler o commit base do branch")
        base_tree = commit_resp.json()["tree"]["sha"]

        # 1. blobs — um por arquivo do lote
        tree_items = []
        for rel, content in files:
            blob_resp = self._request(
                "POST",
                f"/repos/{repo}/git/blobs",
                token=token,
                json={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
            )
            self._check(blob_resp, f"criar o blob de {rel!r}")
            tree_items.append(
                {
                    "path": _join_root(rel, root),
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_resp.json()["sha"],
                }
            )

        # 2. tree + commit — o lote inteiro numa árvore só
        tree_resp = self._request(
            "POST",
            f"/repos/{repo}/git/trees",
            token=token,
            json={"base_tree": base_tree, "tree": tree_items},
        )
        self._check(tree_resp, "criar a árvore do lote")
        new_commit_resp = self._request(
            "POST",
            f"/repos/{repo}/git/commits",
            token=token,
            json={"message": message, "tree": tree_resp.json()["sha"], "parents": [base_commit]},
        )
        self._check(new_commit_resp, "criar o commit do lote")
        sha = new_commit_resp.json()["sha"]

        # 3. atualização da ref — o único passo visível: nunca deixa lote parcial
        ref_resp = self._request(
            "PATCH",
            f"/repos/{repo}/git/refs/heads/{branch}",
            token=token,
            json={"sha": sha, "force": False},
        )
        self._check(ref_resp, f"atualizar o branch {branch!r}")
        return KBCommit(sha=sha, paths=tuple(rel for rel, _ in files))

    # -- delete -------------------------------------------------------------

    def delete(self, path: str, message: str) -> KBCommit:
        """Remove um arquivo do branch via commit atômico (sha: null na tree)."""
        repo, branch, root = self._settings.repo, self._settings.branch, self._settings.root
        token = self._settings.write_token
        if not token:
            raise KBConfigError(
                "KB_WRITE_TOKEN (ou KB_TOKEN com escopo de escrita) não configurado; "
                "a base é somente leitura."
            )
        base_commit = self._ref_commit_sha(token)
        commit_resp = self._request("GET", f"/repos/{repo}/git/commits/{base_commit}", token=token)
        self._check(commit_resp, "ler o commit base do branch")
        base_tree = commit_resp.json()["tree"]["sha"]

        full_path = _join_root(path, root)
        # sha: null marca deleção na Git Data API
        tree_resp = self._request(
            "POST",
            f"/repos/{repo}/git/trees",
            token=token,
            json={
                "base_tree": base_tree,
                "tree": [{"path": full_path, "mode": "100644", "type": "blob", "sha": None}],
            },
        )
        self._check(tree_resp, f"criar tree de remoção de {path!r}")
        new_commit_resp = self._request(
            "POST",
            f"/repos/{repo}/git/commits",
            token=token,
            json={"message": message, "tree": tree_resp.json()["sha"], "parents": [base_commit]},
        )
        self._check(new_commit_resp, f"criar commit de remoção de {path!r}")
        sha = new_commit_resp.json()["sha"]
        ref_resp = self._request(
            "PATCH",
            f"/repos/{repo}/git/refs/heads/{branch}",
            token=token,
            json={"sha": sha, "force": False},
        )
        self._check(ref_resp, f"atualizar o branch {branch!r}")
        return KBCommit(sha=sha, paths=(path,))


class _LocalBackend(_Backend):
    """Backend de dev/testes: mesmas operações sobre KB_LOCAL_PATH."""

    def __init__(self, settings: KBSettings) -> None:
        self._base = settings.local_path
        self._root = settings.root

    def _dir(self) -> Path:
        return self._base if not self._root else self._base / self._root

    def list(self, prefix: str) -> list[str]:
        base = self._dir()
        if not base.is_dir():
            return []
        paths = []
        for entry in sorted(base.rglob("*")):
            if not entry.is_file():
                continue
            rel = entry.relative_to(base).as_posix()
            if prefix and not rel.startswith(prefix):
                continue
            paths.append(rel)
        return paths

    def read(self, path: str) -> KBFile:
        target = self._dir() / path
        if not target.is_file():
            raise KBNotFoundError(f"Arquivo não encontrado na base: {path!r}.")
        return KBFile(path=path, content=target.read_bytes(), content_type=_content_type(path))

    def write(self, files: list[tuple[str, bytes]], message: str) -> KBCommit:
        base = self._dir()
        for rel, content in files:
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return KBCommit(sha="", paths=tuple(rel for rel, _ in files))

    def delete(self, path: str, message: str) -> KBCommit:
        """Remove o arquivo do disco local."""
        target = self._dir() / path
        if not target.is_file():
            raise KBNotFoundError(f"Arquivo não encontrado na base: {path!r}.")
        target.unlink()
        return KBCommit(sha="", paths=(path,))


def _make_backend(settings: KBSettings) -> _Backend:
    if settings.backend == "github":
        return _GithubBackend(settings)
    return _LocalBackend(settings)


# ---------------------------------------------------------------------------
# Cache TTL em memória (por instância)
# ---------------------------------------------------------------------------


class _TTLCache:
    """Cache TTL simples para list/read; write invalida as entradas afetadas."""

    def __init__(self, ttl: float) -> None:
        self._ttl = max(0.0, float(ttl))
        self._lock = threading.Lock()
        self._data: dict[tuple, tuple[float, object]] = {}

    def get(self, key: tuple):
        if self._ttl <= 0:
            return None
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() >= expires_at:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: tuple, value: object) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)

    def invalidate_reads(self, paths: Sequence[str]) -> None:
        with self._lock:
            for path in paths:
                self._data.pop(("read", path), None)

    def invalidate_lists(self) -> None:
        with self._lock:
            for key in [k for k in self._data if k[0] == "list"]:
                self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class KnowledgeBase:
    """Interface única da base: list(prefix), read(path), write(files, message)."""

    def __init__(self, settings: KBSettings | None = None, backend: _Backend | None = None) -> None:
        self.settings = settings or KBSettings.from_env()
        self._backend = backend or _make_backend(self.settings)
        self._cache = _TTLCache(self.settings.cache_ttl)

    def close(self) -> None:
        close = getattr(self._backend, "close", None)
        if callable(close):
            close()

    def list(self, prefix: str = "") -> list[str]:
        key = ("list", prefix)
        cached = self._cache.get(key)
        if cached is not None:
            return list(cached)  # type: ignore[arg-type]
        paths = self._backend.list(prefix)
        self._cache.set(key, tuple(paths))
        return paths

    def read(self, path: str) -> KBFile:
        rel = _normalize_path(path)
        key = ("read", rel)
        cached = self._cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        file = self._backend.read(rel)
        self._cache.set(key, file)
        return file

    def write(self, files: Mapping[str, bytes | str] | Sequence[tuple[str, bytes | str]], message: str) -> KBCommit:
        normalized = _normalize_files(files)
        commit = self._backend.write(normalized, message)
        self._cache.invalidate_reads([path for path, _ in normalized])
        self._cache.invalidate_lists()
        return commit

    def delete(self, path: str, message: str = "") -> KBCommit:
        """Remove um arquivo da base e invalida o cache. Bloqueia `..`."""
        rel = _normalize_path(path)
        commit = self._backend.delete(rel, message or f"kb: remove {rel}")
        self._cache.invalidate_reads([rel])
        self._cache.invalidate_lists()
        return commit

    def render(self, path: str) -> str:
        """Atalho: lê e renderiza como texto (usado pelas tools e pelo qa_cache)."""
        return render_file(self.read(path))


def _normalize_files(
    files: Mapping[str, bytes | str] | Sequence[tuple[str, bytes | str]],
) -> list[tuple[str, bytes]]:
    items = files.items() if isinstance(files, Mapping) else files
    normalized: list[tuple[str, bytes]] = []
    for path, content in items:
        rel = _normalize_path(path)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        normalized.append((rel, data))
    if not normalized:
        raise KBError("Nenhum arquivo para gravar.")
    return normalized


# ---------------------------------------------------------------------------
# Renderizador bytes -> texto (só na leitura; nunca grava no branch)
# ---------------------------------------------------------------------------


def render_file(file: KBFile) -> str:
    """Renderiza um KBFile como texto, conforme o tipo do arquivo."""
    return render_bytes(file.path, file.content, file.content_type)


def render_bytes(path: str, content: bytes, content_type: str = "") -> str:
    """Converte bytes em texto para leitura.

    Regras: csv/tsv -> tabela Markdown; pdf -> texto extraído; texto (md,
    txt, json, … ou UTF-8 válido) -> texto direto; demais binários -> aviso
    com tipo e tamanho.
    """
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _TABLE_SUFFIXES:
        return _render_table(path, content, delimiter=_TABLE_SUFFIXES[suffix])
    if suffix == ".pdf":
        return _render_pdf(path, content)
    text = _decode_text(content)
    if text is not None:
        return text
    return _render_binary_notice(path, content, content_type)


def _decode_text(content: bytes) -> str | None:
    """Decodifica UTF-8; devolve None para bytes que parecem binários."""
    if b"\x00" in content[:4096]:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _render_table(path: str, content: bytes, delimiter: str) -> str:
    text = content.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return f"(tabela vazia: {path})"
    header = rows[0]

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    lines = [
        "| " + " | ".join(cell(c) for c in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        values = [cell(c) for c in row[: len(header)]]
        values += [""] * (len(header) - len(values))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _render_pdf(path: str, content: bytes) -> str:
    try:
        text = _extract_pdf_text_bytes(content)
    except Exception as exc:
        return (
            f"Não foi possível extrair texto do PDF `{path}`: {exc}. "
            "O original continua disponível em GET /kb/file."
        )
    if not text.strip():
        return f"O PDF `{path}` não tem texto extraível (pode ser digitalizado)."
    return text


def _extract_pdf_text_bytes(content: bytes) -> str:
    """Extrai texto de um PDF em memória (mesmo extrator do portal, sem disco).

    Tenta o `pdftotext` (poppler) lendo de stdin e cai para o `pypdf`.
    """
    import shutil
    import subprocess

    errors: list[str] = []
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-", "-"],
                input=content,
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                text = result.stdout.decode("utf-8", errors="replace").strip()
                if text:
                    return text
                errors.append("pdftotext: nenhum texto extraível")
            else:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                errors.append(f"pdftotext: exit {result.returncode} {detail[:200]}")
        except Exception as exc:
            errors.append(f"pdftotext: {exc}")

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        chunks = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n\n".join(chunk for chunk in chunks if chunk).strip()
        if text:
            return text
        errors.append("pypdf: nenhum texto extraível")
    except Exception as exc:
        errors.append(f"pypdf: {exc}")

    raise KBError("; ".join(errors) or "nenhum extrator de PDF disponível")


def _render_binary_notice(path: str, content: bytes, content_type: str) -> str:
    ctype = content_type or _content_type(path) or DEFAULT_CONTENT_TYPE
    return (
        f"Aviso: `{path}` é um arquivo binário (tipo: {ctype}, {len(content)} bytes) "
        "e não é renderizado como texto."
    )


# ---------------------------------------------------------------------------
# Instância padrão (uma por processo; usada pelas tools e endpoints)
# ---------------------------------------------------------------------------

_kb: KnowledgeBase | None = None
_kb_lock = threading.Lock()


def get_kb() -> KnowledgeBase:
    """Devolve o cliente padrão do processo (criado sob demanda)."""
    global _kb
    with _kb_lock:
        if _kb is None:
            _kb = KnowledgeBase()
        return _kb


def reset_kb() -> None:
    """Descarta o cliente padrão (testes / troca de ambiente)."""
    global _kb
    with _kb_lock:
        if _kb is not None:
            _kb.close()
        _kb = None


__all__ = [
    "DEFAULT_BRANCH",
    "DEFAULT_CACHE_TTL_S",
    "KBCommit",
    "KBConfigError",
    "KBError",
    "KBFile",
    "KBAuthError",
    "KBNotFoundError",
    "KBSettings",
    "KBUpstreamError",
    "KnowledgeBase",
    "get_kb",
    "render_bytes",
    "render_file",
    "reset_kb",
]
