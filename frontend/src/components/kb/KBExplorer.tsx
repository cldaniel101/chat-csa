/**
 * KBExplorer — Explorador de arquivos da base de conhecimento.
 *
 * Telas:
 *  - "login": solicita credenciais admin para acessar /kb/*
 *  - "explorer": lista, adiciona, visualiza e remove documentos; botão para iniciar chatbot
 *
 * Fluxo:
 *  1. Usuário faz login → token guardado em sessionStorage
 *  2. Lista de documentos carregada via GET /kb/list
 *  3. Upload via POST /kb/upload (multipart)
 *  4. Abertura via GET /kb/file com header de auth → preview renderizado no front
 *  5. Remoção: modal de confirmação → DELETE /kb/file → commit atômico no branch data
 *  6. Iniciar chatbot: modal de confirmação → callback para abrir o widget
 */

import { BsStars } from "react-icons/bs";
import {
  AlertTriangle,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileText,
  FolderInput,
  FolderOpen,
  LogOut,
  MessageCircle,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  authLogin,
  getConsumerUrl,
  kbDelete,
  kbFile,
  kbFileUpdate,
  kbList,
  kbMove,
  kbUpload,
  UnauthorizedError,
  type KBUploadFileResult,
} from "../../api/client";
import "./KBExplorer.css";

// ─── Chave de sessão ──────────────────────────────────────────────────────────

const SESSION_KEY = "kbe_token";

function saveToken(token: string) {
  try {
    sessionStorage.setItem(SESSION_KEY, token);
  } catch {
    /* sem suporte a sessionStorage — ignora */
  }
}

function loadToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function clearToken() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignora */
  }
}

// ─── Seção de destino do upload ───────────────────────────────────────────────

const UPLOAD_SECTION_KEY = "kbe_upload_section";

function loadUploadSection(): string {
  try {
    return localStorage.getItem(UPLOAD_SECTION_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveUploadSection(section: string) {
  try {
    localStorage.setItem(UPLOAD_SECTION_KEY, section);
  } catch {
    /* ignora */
  }
}

// ─── Utilidades de path ───────────────────────────────────────────────────────

/** Extrai o slug (nome sem extensão) do último segmento do caminho. */
function pathToName(path: string): string {
  const segments = path.split("/");
  const last = segments[segments.length - 1] ?? path;
  const dotIdx = last.lastIndexOf(".");
  return dotIdx > 0 ? last.slice(0, dotIdx) : last;
}

/** Extrai a categoria do primeiro segmento do caminho. */
function pathToCategory(path: string): string {
  const segments = path.split("/");
  if (segments.length > 1) {
    return segments[0].replace(/-/g, " ");
  }
  return "raiz";
}

/** Formata um rótulo de categoria legível. */
function formatCategory(raw: string): string {
  return raw
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// ─── Tipos ────────────────────────────────────────────────────────────────────

type KBFile = {
  path: string;
  name: string;
  category: string;
  author: string;
  uploaded_at: string;
};

/** Limites de segurança para evitar congelamento ao renderizar Markdown extenso. */
const MAX_MARKDOWN_PREVIEW_LINES = 150;
const MAX_MARKDOWN_PREVIEW_BYTES = 250 * 1024; // 250 KB

/** Como o preview no front renderiza cada tipo de arquivo. */
type PreviewKind = "markdown" | "text" | "image" | "pdf" | "binary";

type PreviewState = {
  file: KBFile;
  kind: PreviewKind;
  contentType: string;
  size: number;
  text?: string;
  objectUrl: string;
};

/** Decide o modo de preview a partir da extensão/content-type. */
function previewKind(path: string, contentType: string): PreviewKind {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "md" || ext === "markdown" || contentType === "text/markdown") {
    return "markdown";
  }
  if (contentType.startsWith("image/")) {
    return "image";
  }
  if (contentType === "application/pdf" || ext === "pdf") {
    return "pdf";
  }
  if (
    contentType.startsWith("text/") ||
    contentType === "application/json" ||
    contentType.endsWith("+json") ||
    contentType === "application/xml" ||
    contentType.endsWith("+xml") ||
    contentType === "application/javascript"
  ) {
    return "text";
  }
  return "binary";
}

/** Formata bytes para exibição no preview. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type Screen = "login" | "explorer";

type KBExplorerProps = {
  /** Chamado quando o usuário confirma o início de uma conversa. */
  onStartChat: () => void;
};

// ─── Modal de confirmação genérico ────────────────────────────────────────────

type ConfirmModalProps = {
  icon: "chat" | "danger" | "upload";
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

function ConfirmModal({
  icon,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancelar",
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  return (
    <div
      className="kbe-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="kbe-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="kbe-modal">
        <div className="kbe-modal-header">
          <span className={`kbe-modal-header-icon kbe-modal-header-icon--${icon}`} aria-hidden="true">
            {icon === "chat" ? <MessageCircle size={20} /> : icon === "upload" ? <Upload size={20} /> : <AlertTriangle size={20} />}
          </span>
          <h3 id="kbe-modal-title">{title}</h3>
        </div>
        <div className="kbe-modal-body">{body}</div>
        <div className="kbe-modal-footer">
          <button
            id="kbe-modal-cancel"
            type="button"
            className="kbe-btn kbe-btn--ghost"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            id="kbe-modal-confirm"
            type="button"
            className={`kbe-btn ${icon === "danger" ? "kbe-btn--danger" : "kbe-btn--primary"}`}
            onClick={onConfirm}
            disabled={confirmDisabled}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Tela de login ────────────────────────────────────────────────────────────

type LoginScreenProps = {
  onSuccess: (token: string) => void;
};

function LoginScreen({ onSuccess }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const result = await authLogin(username.trim(), password);
      saveToken(result.access_token);
      onSuccess(result.access_token);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro desconhecido.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="kbe-login-root">
      <div className="kbe-login-card">
        <div className="kbe-login-header">
          <span className="kbe-login-header-icon" aria-hidden="true">
            <FolderOpen size={24} />
          </span>
          <h1>Base de Conhecimento</h1>
          <p>Acesso restrito ao time de curadoria.</p>
        </div>

        <form className="kbe-login-body" onSubmit={handleSubmit} noValidate>
          {error && (
            <div className="kbe-alert kbe-alert--error" role="alert">
              <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
              {error}
            </div>
          )}

          <div>
            <label htmlFor="kbe-username">Usuário</label>
            <input
              id="kbe-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div>
            <label htmlFor="kbe-password">Senha</label>
            <input
              id="kbe-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <button
            id="kbe-login-submit"
            type="submit"
            className="kbe-btn kbe-btn--primary"
            disabled={loading || !username.trim() || !password.trim()}
            style={{ marginTop: 4 }}
          >
            {loading ? "Entrando…" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Explorador principal ─────────────────────────────────────────────────────

type ExplorerScreenProps = {
  token: string;
  onLogout: () => void;
  onStartChat: () => void;
};

function ExplorerScreen({ token, onLogout, onStartChat }: ExplorerScreenProps) {
  const [files, setFiles] = useState<KBFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Feedback de upload */
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<KBUploadFileResult[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  /* Arquivos escolhidos aguardando a seção de destino */
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null);
  const [uploadSection, setUploadSection] = useState<string>(() => loadUploadSection());

  /* Remoção */
  const [deleteTarget, setDeleteTarget] = useState<KBFile | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  /* Busca, filtros de categoria e paginação */
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 15;

  /* Edição inline */
  const [editTarget, setEditTarget] = useState<KBFile | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  /* Renomeação e movimentação */
  const [renameTarget, setRenameTarget] = useState<KBFile | null>(null);
  const [renameNewPath, setRenameNewPath] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameError, setRenameError] = useState<string | null>(null);

  /* Modal de confirmação para chatbot */
  const [showChatConfirm, setShowChatConfirm] = useState(false);

  /* Preview do arquivo (renderizado no front, token no header) */
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [lastOpenedFile, setLastOpenedFile] = useState<KBFile | null>(null);
  const previewAbortControllerRef = useRef<AbortController | null>(null);

  /* Truncamento e teto de segurança para evitar congelamento do renderer em Markdowns volumosos */
  const markdownPreviewInfo = useMemo(() => {
    if (!preview || preview.kind !== "markdown" || !preview.text) {
      return null;
    }
    const lines = preview.text.split("\n");
    const totalLines = lines.length;
    const isTruncated = preview.size > MAX_MARKDOWN_PREVIEW_BYTES || totalLines > MAX_MARKDOWN_PREVIEW_LINES;
    const content = isTruncated ? lines.slice(0, MAX_MARKDOWN_PREVIEW_LINES).join("\n") : preview.text;
    return {
      isTruncated,
      totalLines,
      content,
    };
  }, [preview]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  /* Revoga a object URL do preview ao trocar/fechar o documento */
  useEffect(() => {
    return () => {
      if (preview?.objectUrl) URL.revokeObjectURL(preview.objectUrl);
    };
  }, [preview]);

  /* Carrega lista de documentos */
  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUploadResults(null);
    setUploadError(null);

    try {
      const result = await kbList(token);
      const metaMap = new Map((result.files ?? []).map((f) => [f.path, f]));
      const parsed: KBFile[] = result.paths.map((p) => {
        const meta = metaMap.get(p);
        return {
          path: p,
          name: pathToName(p),
          category: formatCategory(pathToCategory(p)),
          author: meta?.author || "admin",
          uploaded_at: meta?.uploaded_at || "–",
        };
      });
      setFiles(parsed);
    } catch (err: unknown) {
      /* Token expirado ou inválido → volta para o login */
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Erro ao carregar a lista.");
    } finally {
      setLoading(false);
    }
  }, [token, onLogout]);

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- carregamento assíncrono de dados externos é o padrão correto aqui
    void loadFiles();
  }, [loadFiles]);

  /* Upload de arquivos */
  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    if (!selected.length) return;
    /* Abre o modal para declarar a seção antes de enviar */
    setPendingFiles(selected);
    /* Limpa o input para permitir reenvio do mesmo arquivo */
    e.target.value = "";
  }

  /* Envia o lote com o caminho `<seção>/<arquivo>` exigido pelo servidor */
  function handleUploadConfirm() {
    if (!pendingFiles) return;
    const section = uploadSection.trim().replace(/^\/+|\/+$/g, "");
    if (!section) return;
    saveUploadSection(section);
    setUploadSection(section);
    const selected = pendingFiles;
    setPendingFiles(null);
    void doUpload(selected, section);
  }

  async function doUpload(selected: File[], section: string) {
    setUploading(true);
    setUploadResults(null);
    setUploadError(null);

    try {
      const result = await kbUpload(token, selected, { section });
      setUploadResults(result.files);
      /* Recarrega a lista após upload bem-sucedido */
      if (result.ok) {
        await loadFiles();
      }
    } catch (err: unknown) {
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      setUploadError(err instanceof Error ? err.message : "Erro durante o upload.");
    } finally {
      setUploading(false);
    }
  }

  /* Abre o preview no front: baixa os bytes com o header de auth e renderiza aqui */
  async function handleOpen(file: KBFile) {
    if (previewAbortControllerRef.current) {
      previewAbortControllerRef.current.abort();
    }
    const controller = new AbortController();
    previewAbortControllerRef.current = controller;
    setLastOpenedFile(file);
    setPreviewError(null);
    setPreviewLoading(file.path);

    try {
      const { blob, contentType } = await kbFile(token, file.path, {
        signal: controller.signal,
        timeoutMs: 15000,
      });
      const kind = previewKind(file.path, contentType);
      setPreview({
        file,
        kind,
        contentType,
        size: blob.size,
        objectUrl: URL.createObjectURL(blob),
        text: kind === "markdown" || kind === "text" ? await blob.text() : undefined,
      });
    } catch (err: unknown) {
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      if (err instanceof Error && err.message === "Carregamento do arquivo cancelado.") {
        return;
      }
      setPreviewError(err instanceof Error ? err.message : "Erro ao abrir o arquivo.");
    } finally {
      if (previewAbortControllerRef.current === controller) {
        previewAbortControllerRef.current = null;
      }
      setPreviewLoading(null);
    }
  }

  function handleCancelPreview() {
    if (previewAbortControllerRef.current) {
      previewAbortControllerRef.current.abort();
      previewAbortControllerRef.current = null;
    }
    setPreviewLoading(null);
  }

  /* Fecha o preview (a object URL é revogada no efeito de limpeza) */
  function closePreview() {
    setPreview(null);
  }

  /* Baixa o arquivo aberto usando a object URL já carregada */
  function handleDownload() {
    if (!preview) return;
    const link = document.createElement("a");
    link.href = preview.objectUrl;
    link.download = preview.file.path.split("/").pop() || "documento";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  /* Remoção */
  function handleDeleteRequest(file: KBFile) {
    setDeleteError(null);
    setDeleteTarget(file);
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    const target = deleteTarget;
    setDeleteTarget(null);

    try {
      await kbDelete(token, target.path);
      /* Atualiza a lista após remoção bem-sucedida */
      await loadFiles();
    } catch (err: unknown) {
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      setDeleteError(err instanceof Error ? err.message : "Erro ao remover o arquivo.");
    } finally {
      setDeleting(false);
    }
  }

  /* Iniciar chatbot */
  function handleChatConfirm() {
    setShowChatConfirm(false);
    onStartChat();
  }

  /* Busca e filtros de categoria */
  const categories = useMemo(() => {
    const set = new Set(files.map((f) => f.category));
    return Array.from(set).sort();
  }, [files]);

  const filteredFiles = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return files.filter((f) => {
      const matchesCategory = selectedCategory === "all" || f.category === selectedCategory;
      const matchesSearch =
        !q || f.path.toLowerCase().includes(q) || f.name.toLowerCase().includes(q);
      return matchesCategory && matchesSearch;
    });
  }, [files, searchQuery, selectedCategory]);

  const totalPages = Math.max(1, Math.ceil(filteredFiles.length / PAGE_SIZE));
  const paginatedFiles = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredFiles.slice(start, start + PAGE_SIZE);
  }, [filteredFiles, currentPage]);

  function handleSearchChange(value: string) {
    setSearchQuery(value);
    setCurrentPage(1);
  }

  function handleCategoryChange(value: string) {
    setSelectedCategory(value);
    setCurrentPage(1);
  }

  /* Edição inline */
  async function handleOpenEdit(file: KBFile) {
    setEditError(null);
    setEditLoading(true);
    setEditTarget(file);
    try {
      const { blob } = await kbFile(token, file.path);
      const text = await blob.text();
      setEditContent(text);
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : "Erro ao carregar conteúdo do arquivo.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleSaveEdit() {
    if (!editTarget) return;
    setEditSaving(true);
    setEditError(null);
    try {
      await kbFileUpdate(token, editTarget.path, editContent);
      setEditTarget(null);
      await loadFiles();
    } catch (err: unknown) {
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      setEditError(err instanceof Error ? err.message : "Erro ao salvar alterações.");
    } finally {
      setEditSaving(false);
    }
  }

  /* Renomeação / Mover */
  function handleOpenRename(file: KBFile) {
    setRenameError(null);
    setRenameTarget(file);
    setRenameNewPath(file.path);
  }

  async function handleConfirmRename() {
    if (!renameTarget) return;
    const trimmed = renameNewPath.trim();
    if (!trimmed || trimmed === renameTarget.path) {
      setRenameTarget(null);
      return;
    }
    setRenaming(true);
    setRenameError(null);
    try {
      await kbMove(token, renameTarget.path, trimmed);
      setRenameTarget(null);
      await loadFiles();
    } catch (err: unknown) {
      if (err instanceof UnauthorizedError) {
        clearToken();
        onLogout();
        return;
      }
      setRenameError(err instanceof Error ? err.message : "Erro ao renomear arquivo.");
    } finally {
      setRenaming(false);
    }
  }

  /* Seções já existentes na base (primeiro segmento dos caminhos) */
  const sections = Array.from(
    new Set(
      files
        .filter((file) => file.path.includes("/"))
        .map((file) => file.path.split("/")[0]),
    ),
  ).sort();

  return (
    <div className="kbe-root">
      {/* Cabeçalho */}
      <header className="kbe-topbar">
        <div className="kbe-topbar-logo">
          <span className="kbe-topbar-logo-icon" aria-hidden="true">
            <BsStars size={18} />
          </span>
          <div>
            <h1>Base de Conhecimento</h1>
            <p className="kbe-topbar-sub">Chat CSA · {getConsumerUrl()}</p>
          </div>
        </div>

        <div className="kbe-topbar-spacer" />

        {/* Botão de iniciar chatbot */}
        <button
          id="kbe-start-chat-btn"
          type="button"
          className="kbe-btn kbe-btn--chat"
          onClick={() => setShowChatConfirm(true)}
        >
          <MessageCircle size={16} aria-hidden="true" />
          Iniciar Chatbot
        </button>

        {/* Logout */}
        <button
          id="kbe-logout-btn"
          type="button"
          className="kbe-btn kbe-btn--ghost"
          style={{ color: "rgba(255,255,255,0.9)", borderColor: "rgba(255,255,255,0.35)" }}
          onClick={() => { clearToken(); onLogout(); }}
          title="Sair"
          aria-label="Sair da sessão admin"
        >
          <LogOut size={15} aria-hidden="true" />
          Sair
        </button>
      </header>

      {/* Corpo */}
      <main className="kbe-body">

        {/* Feedback de upload */}
        {uploadError && (
          <div className="kbe-alert kbe-alert--error" role="alert">
            <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
            {uploadError}
          </div>
        )}
        {deleteError && (
          <div className="kbe-alert kbe-alert--error" role="alert">
            <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
            {deleteError}
          </div>
        )}
        {deleting && (
          <div className="kbe-alert kbe-alert--info" role="status">
            <div className="kbe-spinner" aria-hidden="true" />
            Removendo arquivo…
          </div>
        )}
        {previewLoading && (
          <div
            className="kbe-alert kbe-alert--info"
            role="status"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <div className="kbe-spinner" aria-hidden="true" />
              <span>Abrindo <strong>{previewLoading}</strong>…</span>
            </div>
            <button
              id="kbe-cancel-preview-btn"
              type="button"
              className="kbe-btn kbe-btn--ghost"
              style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={handleCancelPreview}
            >
              Cancelar
            </button>
          </div>
        )}
        {previewError && (
          <div
            className="kbe-alert kbe-alert--error"
            role="alert"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-sm)" }}>
              <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
              <span>{previewError}</span>
            </div>
            <div style={{ display: "flex", gap: "var(--sp-xs)" }}>
              {lastOpenedFile && (
                <button
                  id="kbe-retry-preview-btn"
                  type="button"
                  className="kbe-btn kbe-btn--ghost"
                  style={{ padding: "4px 10px", fontSize: 12 }}
                  onClick={() => { void handleOpen(lastOpenedFile); }}
                >
                  Tentar novamente
                </button>
              )}
              <button
                type="button"
                className="kbe-icon-btn"
                onClick={() => setPreviewError(null)}
                aria-label="Dispensar aviso"
                title="Dispensar"
              >
                <XCircle size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
        {uploading && (
          <div className="kbe-alert kbe-alert--info" role="status">
            <div className="kbe-spinner" aria-hidden="true" />
            Enviando e convertendo arquivo(s)…
          </div>
        )}
        {uploadResults && !uploading && (
          <div className="kbe-alert kbe-alert--success" role="status">
            <CheckCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
            <div>
              Upload concluído.
              <div className="kbe-upload-results">
                {uploadResults.map((r) => (
                  <span
                    key={r.path}
                    className={`kbe-upload-result-item kbe-upload-result-item--${r.ok && r.converted ? "ok" : "fail"}`}
                  >
                    {r.ok && r.converted ? (
                      <CheckCircle size={12} aria-hidden="true" />
                    ) : (
                      <XCircle size={12} aria-hidden="true" />
                    )}
                    {r.path}
                    {r.error ? ` — ${r.error}` : ""}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Cartão principal de arquivos */}
        <div className="kbe-card">
          {/* Toolbar */}
          <div className="kbe-toolbar">
            <h2 className="kbe-toolbar-title">
              Documentos
              {!loading && !error && (
                <span className="kbe-toolbar-count"> ({files.length})</span>
              )}
            </h2>

            <button
              id="kbe-refresh-btn"
              type="button"
              className="kbe-btn kbe-btn--ghost"
              onClick={() => { void loadFiles(); }}
              disabled={loading || uploading}
              aria-label="Recarregar lista de documentos"
              title="Recarregar"
            >
              <RefreshCw size={14} aria-hidden="true" />
              Atualizar
            </button>

            {/* Input de arquivo oculto */}
            <input
              ref={fileInputRef}
              type="file"
              className="kbe-file-input-hidden"
              id="kbe-file-input"
              multiple
              accept=".md,.txt,.pdf,.csv,.tsv,.json,.png,.jpg,.jpeg,.webp"
              onChange={handleFileInputChange}
              aria-label="Selecionar arquivos para upload"
            />
            <button
              id="kbe-upload-btn"
              type="button"
              className="kbe-btn kbe-btn--primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Upload size={14} aria-hidden="true" />
              Adicionar arquivo
            </button>
          </div>

          {/* Barra de busca e filtros */}
          {!loading && !error && files.length > 0 && (
            <div className="kbe-filters-bar">
              <div className="kbe-search-input-wrap">
                <Search size={15} className="kbe-search-icon" aria-hidden="true" />
                <input
                  id="kbe-search-input"
                  type="text"
                  className="kbe-search-input"
                  placeholder="Buscar por nome ou caminho…"
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  aria-label="Buscar documentos"
                />
              </div>

              <select
                id="kbe-category-select"
                className="kbe-category-select"
                value={selectedCategory}
                onChange={(e) => handleCategoryChange(e.target.value)}
                aria-label="Filtrar por categoria"
              >
                <option value="all">Todas as categorias ({files.length})</option>
                {categories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat} ({files.filter((f) => f.category === cat).length})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Conteúdo */}
          {loading ? (
            <div className="kbe-loading" role="status" aria-live="polite">
              <div className="kbe-spinner" aria-hidden="true" />
              Carregando documentos…
            </div>
          ) : error ? (
            <div className="kbe-alert kbe-alert--error" style={{ margin: "var(--sp-lg)" }} role="alert">
              <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
              {error}
            </div>
          ) : files.length === 0 ? (
            <div className="kbe-empty">
              <span className="kbe-empty-icon" aria-hidden="true">
                <FileText size={26} />
              </span>
              <h3>Nenhum documento na base</h3>
              <p>
                Use o botão <strong>Adicionar arquivo</strong> para enviar o
                primeiro documento ao branch <code>data</code>.
              </p>
            </div>
          ) : (
            <div className="kbe-table-wrap">
              <table className="kbe-table" aria-label="Lista de documentos da base de conhecimento">
                <thead>
                  <tr>
                    <th scope="col" className="kbe-col-name">Nome / Caminho</th>
                    <th scope="col" className="kbe-col-category">Categoria</th>
                    <th scope="col" className="kbe-col-author">Enviado por</th>
                    <th scope="col" className="kbe-col-date">Data de adição</th>
                    <th scope="col" className="kbe-col-actions">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedFiles.map((file) => {
                    return (
                      <tr key={file.path}>
                        <td className="kbe-col-name">
                          <div className="kbe-file-name">{file.name.replace(/-/g, " ")}</div>
                          <div className="kbe-file-path">{file.path}</div>
                        </td>
                        <td className="kbe-col-category">
                          <span className="kbe-badge">{file.category}</span>
                        </td>
                        <td className="kbe-col-author" style={{ fontSize: 13, color: "var(--c-muted)" }}>
                          {file.author}
                        </td>
                        <td className="kbe-col-date" style={{ fontSize: 12, color: "var(--c-muted)" }}>
                          {file.uploaded_at}
                        </td>
                        <td className="kbe-col-actions">
                          <div className="kbe-row-actions">
                            {/* Abrir arquivo */}
                            <button
                              type="button"
                              className="kbe-icon-btn"
                              onClick={() => { void handleOpen(file); }}
                              disabled={previewLoading === file.path}
                              aria-label={`Abrir ${file.name}`}
                              title="Abrir / visualizar"
                            >
                              <Eye size={16} aria-hidden="true" />
                            </button>

                            {/* Editar texto inline */}
                            <button
                              type="button"
                              className="kbe-icon-btn"
                              onClick={() => { void handleOpenEdit(file); }}
                              disabled={editLoading || editSaving}
                              aria-label={`Editar ${file.name}`}
                              title="Editar texto inline"
                            >
                              <Pencil size={15} aria-hidden="true" />
                            </button>

                            {/* Renomear / Mover */}
                            <button
                              type="button"
                              className="kbe-icon-btn"
                              onClick={() => handleOpenRename(file)}
                              disabled={renaming}
                              aria-label={`Renomear ${file.name}`}
                              title="Renomear ou mover arquivo"
                            >
                              <FolderInput size={15} aria-hidden="true" />
                            </button>

                            {/* Remover arquivo */}
                            <button
                              type="button"
                              className="kbe-icon-btn kbe-icon-btn--danger"
                              onClick={() => handleDeleteRequest(file)}
                              disabled={deleting || uploading}
                              aria-label={`Remover ${file.name}`}
                              title="Remover documento"
                            >
                              <Trash2 size={15} aria-hidden="true" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Paginação */}
              {totalPages > 1 && (
                <div className="kbe-pagination">
                  <div>
                    Mostrando {(currentPage - 1) * PAGE_SIZE + 1}–
                    {Math.min(currentPage * PAGE_SIZE, filteredFiles.length)} de {filteredFiles.length} documentos
                  </div>
                  <div className="kbe-pagination-controls">
                    <button
                      type="button"
                      className="kbe-pagination-btn"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      aria-label="Página anterior"
                    >
                      <ChevronLeft size={16} aria-hidden="true" />
                    </button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                      <button
                        key={page}
                        type="button"
                        className={`kbe-pagination-btn ${page === currentPage ? "kbe-pagination-btn--active" : ""}`}
                        onClick={() => setCurrentPage(page)}
                        aria-label={`Página ${page}`}
                        aria-current={page === currentPage ? "page" : undefined}
                      >
                        {page}
                      </button>
                    ))}
                    <button
                      type="button"
                      className="kbe-pagination-btn"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages}
                      aria-label="Próxima página"
                    >
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Rodapé com ação de chatbot */}
          {!loading && !error && (
            <div className="kbe-footer-actions">
              <button
                id="kbe-footer-start-chat-btn"
                type="button"
                className="kbe-btn kbe-btn--chat"
                onClick={() => setShowChatConfirm(true)}
              >
                <MessageCircle size={15} aria-hidden="true" />
                Iniciar conversa com o chatbot
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Modal: destino do upload */}
      {pendingFiles && (
        <ConfirmModal
          icon="upload"
          title={
            pendingFiles.length > 1
              ? `Enviar ${pendingFiles.length} arquivos?`
              : "Enviar arquivo?"
          }
          confirmLabel="Enviar"
          confirmDisabled={!uploadSection.trim()}
          onConfirm={handleUploadConfirm}
          onCancel={() => setPendingFiles(null)}
          body={
            <>
              <ul className="kbe-upload-file-list">
                {pendingFiles.map((file) => (
                  <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                    {file.name}
                  </li>
                ))}
              </ul>
              <label htmlFor="kbe-upload-section" className="kbe-upload-label">
                Seção de destino
              </label>
              <input
                id="kbe-upload-section"
                className="kbe-upload-input"
                type="text"
                list="kbe-upload-sections"
                placeholder="ex.: editais"
                value={uploadSection}
                onChange={(e) => setUploadSection(e.target.value)}
              />
              <datalist id="kbe-upload-sections">
                {sections.map((section) => (
                  <option key={section} value={section} />
                ))}
              </datalist>
              <p className="kbe-upload-hint">
                Cada arquivo vira um conceito <code>&lt;seção&gt;/&lt;nome&gt;.md</code> num
                único commit no branch <code>data</code>; o original não é preservado.
              </p>
            </>
          }
        />
      )}

      {/* Modal: preview do documento renderizado no front */}
      {preview && (
        <div
          className="kbe-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="kbe-preview-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closePreview();
          }}
        >
          <div className="kbe-modal kbe-modal--preview">
            <div className="kbe-modal-header">
              <span className="kbe-modal-header-icon kbe-modal-header-icon--chat" aria-hidden="true">
                <FileText size={18} />
              </span>
              <div className="kbe-preview-heading">
                <h3 id="kbe-preview-title">{preview.file.name.replace(/-/g, " ")}</h3>
                <p className="kbe-preview-sub">{preview.file.path}</p>
              </div>
              <button
                type="button"
                className="kbe-icon-btn"
                onClick={closePreview}
                aria-label="Fechar visualização"
                title="Fechar"
              >
                <XCircle size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="kbe-preview-body">
              {preview.kind === "markdown" && (
                <div className="kbe-preview-markdown">
                  {markdownPreviewInfo?.isTruncated && (
                    <div
                      className="kbe-alert kbe-alert--info kbe-preview-truncated-alert"
                      role="alert"
                      style={{ marginBottom: "var(--sp-md)" }}
                    >
                      <AlertTriangle size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <strong>Documento extenso detectado ({markdownPreviewInfo.totalLines.toLocaleString("pt-BR")} linhas, {formatBytes(preview.size)}).</strong>
                        <p style={{ margin: "4px 0 0" }}>
                          Exibindo apenas os primeiros {MAX_MARKDOWN_PREVIEW_LINES} registros para evitar lentidão ou travamento do navegador. Baixe o documento para consultar o conteúdo completo.
                        </p>
                      </div>
                      <button
                        type="button"
                        className="kbe-btn kbe-btn--ghost"
                        onClick={handleDownload}
                        style={{ alignSelf: "center", whiteSpace: "nowrap" }}
                      >
                        <Download size={14} aria-hidden="true" />
                        Baixar original
                      </button>
                    </div>
                  )}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {markdownPreviewInfo ? markdownPreviewInfo.content : (preview.text ?? "")}
                  </ReactMarkdown>
                </div>
              )}

              {preview.kind === "text" && (
                <pre className="kbe-preview-text">{preview.text ?? ""}</pre>
              )}

              {preview.kind === "image" && (
                <img className="kbe-preview-image" src={preview.objectUrl} alt={preview.file.name} />
              )}

              {preview.kind === "pdf" && (
                <iframe
                  className="kbe-preview-pdf"
                  src={preview.objectUrl}
                  title={preview.file.name}
                />
              )}

              {preview.kind === "binary" && (
                <div className="kbe-preview-binary">
                  <FileText size={30} aria-hidden="true" />
                  <p>Este formato não pode ser exibido no navegador.</p>
                  <p className="kbe-preview-meta">
                    {preview.contentType} · {formatBytes(preview.size)}
                  </p>
                </div>
              )}
            </div>

            <div className="kbe-modal-footer">
              <button type="button" className="kbe-btn kbe-btn--ghost" onClick={closePreview}>
                Fechar
              </button>
              <button
                id="kbe-preview-download"
                type="button"
                className="kbe-btn kbe-btn--primary"
                onClick={handleDownload}
              >
                <Download size={14} aria-hidden="true" />
                Baixar original
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: confirmação de remoção */}
      {deleteTarget && (
        <ConfirmModal
          icon="danger"
          title="Remover documento?"
          body={
            <>
              <p>
                Tem certeza que deseja remover permanentemente o arquivo:
              </p>
              <p style={{ fontFamily: "monospace", fontSize: 12, wordBreak: "break-all" }}>
                {deleteTarget.path}
              </p>
              <p style={{ color: "var(--c-muted)", fontSize: 12 }}>
                <AlertTriangle size={12} style={{ verticalAlign: "middle", marginRight: 4 }} aria-hidden="true" />
                Esta ação cria um commit no branch <code>data</code> e não pode ser desfeita
                pelo painel.
              </p>
            </>
          }
          confirmLabel="Sim, remover"
          onConfirm={() => { void handleDeleteConfirm(); }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Modal: confirmação para iniciar chatbot */}
      {showChatConfirm && (
        <ConfirmModal
          icon="chat"
          title="Iniciar conversa?"
          body={
            <>
              <p>
                Deseja iniciar uma conversa utilizando os documentos
                disponíveis na base?
              </p>
              {files.length === 0 && (
                <p style={{ color: "var(--c-muted)", fontSize: 12 }}>
                  <AlertTriangle size={12} style={{ verticalAlign: "middle", marginRight: 4 }} aria-hidden="true" />
                  A base está vazia. O chatbot responderá que não encontrou
                  a informação solicitada.
                </p>
              )}
            </>
          }
          confirmLabel="Sim, iniciar"
          onConfirm={handleChatConfirm}
          onCancel={() => setShowChatConfirm(false)}
        />
      )}

      {/* Modal: Edição inline */}
      {editTarget && (
        <div
          className="kbe-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="kbe-edit-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !editSaving) setEditTarget(null);
          }}
        >
          <div className="kbe-modal kbe-modal--preview">
            <div className="kbe-modal-header">
              <span className="kbe-modal-header-icon kbe-modal-header-icon--chat" aria-hidden="true">
                <Pencil size={18} />
              </span>
              <div className="kbe-preview-heading">
                <h3 id="kbe-edit-title">Editar documento</h3>
                <p className="kbe-preview-sub">{editTarget.path}</p>
              </div>
              <button
                type="button"
                className="kbe-icon-btn"
                onClick={() => setEditTarget(null)}
                disabled={editSaving}
                aria-label="Fechar edição"
                title="Fechar"
              >
                <XCircle size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="kbe-preview-body" style={{ padding: "var(--sp-md)" }}>
              {editError && (
                <div className="kbe-alert kbe-alert--error" style={{ marginBottom: "var(--sp-sm)" }} role="alert">
                  <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                  {editError}
                </div>
              )}
              {editLoading ? (
                <div className="kbe-loading">
                  <div className="kbe-spinner" aria-hidden="true" />
                  Carregando conteúdo…
                </div>
              ) : (
                <textarea
                  id="kbe-edit-textarea"
                  className="kbe-edit-textarea"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={18}
                  placeholder="Conteúdo do documento em Markdown ou texto…"
                  disabled={editSaving}
                />
              )}
            </div>

            <div className="kbe-modal-footer">
              <button
                type="button"
                className="kbe-btn kbe-btn--ghost"
                onClick={() => setEditTarget(null)}
                disabled={editSaving}
              >
                Cancelar
              </button>
              <button
                id="kbe-save-edit-btn"
                type="button"
                className="kbe-btn kbe-btn--primary"
                onClick={() => { void handleSaveEdit(); }}
                disabled={editSaving || editLoading}
              >
                {editSaving ? "Salvando…" : "Salvar alterações"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Renomear ou Mover */}
      {renameTarget && (
        <ConfirmModal
          icon="upload"
          title="Renomear ou mover arquivo"
          confirmLabel={renaming ? "Salvando…" : "Confirmar"}
          confirmDisabled={renaming || !renameNewPath.trim() || renameNewPath.trim() === renameTarget.path}
          onConfirm={() => { void handleConfirmRename(); }}
          onCancel={() => { if (!renaming) setRenameTarget(null); }}
          body={
            <>
              <p>
                Altere o caminho para renomear ou mover o arquivo para outra categoria:
              </p>
              <div style={{ margin: "var(--sp-sm) 0" }}>
                <label htmlFor="kbe-rename-input" style={{ display: "block", fontSize: 12, color: "var(--c-muted)", marginBottom: 4 }}>
                  Novo caminho relativo à raiz da base:
                </label>
                <input
                  id="kbe-rename-input"
                  type="text"
                  className="kbe-search-input"
                  style={{ paddingLeft: 10 }}
                  value={renameNewPath}
                  onChange={(e) => setRenameNewPath(e.target.value)}
                  placeholder="ex: editais/novo_nome.md"
                  disabled={renaming}
                />
              </div>
              {renameError && (
                <div className="kbe-alert kbe-alert--error" role="alert" style={{ marginTop: "var(--sp-sm)" }}>
                  <XCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                  {renameError}
                </div>
              )}
            </>
          }
        />
      )}
    </div>
  );
}

// ─── Componente raiz: KBExplorer ──────────────────────────────────────────────

export function KBExplorer({ onStartChat }: KBExplorerProps) {
  const [screen, setScreen] = useState<Screen>(() =>
    loadToken() ? "explorer" : "login",
  );
  const [token, setToken] = useState<string>(() => loadToken() ?? "");

  function handleLoginSuccess(newToken: string) {
    setToken(newToken);
    setScreen("explorer");
  }

  function handleLogout() {
    setToken("");
    setScreen("login");
  }

  if (screen === "login") {
    return <LoginScreen onSuccess={handleLoginSuccess} />;
  }

  return (
    <ExplorerScreen
      token={token}
      onLogout={handleLogout}
      onStartChat={onStartChat}
    />
  );
}
