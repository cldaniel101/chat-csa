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
 *  4. Abertura via GET /kb/file (abre em nova aba)
 *  5. Remoção: modal de confirmação → DELETE /kb/file → commit atômico no branch data
 *  6. Iniciar chatbot: modal de confirmação → callback para abrir o widget
 */

import { BsStars } from "react-icons/bs";
import {
  AlertTriangle,
  CheckCircle,
  Eye,
  FileText,
  FolderOpen,
  LogOut,
  MessageCircle,
  RefreshCw,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  authLogin,
  getConsumerUrl,
  kbDelete,
  kbFileUrl,
  kbList,
  kbUpload,
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
};

type Screen = "login" | "explorer";

type KBExplorerProps = {
  /** Chamado quando o usuário confirma o início de uma conversa. */
  onStartChat: () => void;
};

// ─── Modal de confirmação genérico ────────────────────────────────────────────

type ConfirmModalProps = {
  icon: "chat" | "danger";
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

function ConfirmModal({
  icon,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancelar",
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
            {icon === "chat" ? <MessageCircle size={20} /> : <AlertTriangle size={20} />}
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

  /* Remoção */
  const [deleteTarget, setDeleteTarget] = useState<KBFile | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  /* Modal de confirmação para chatbot */
  const [showChatConfirm, setShowChatConfirm] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  /* Carrega lista de documentos */
  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUploadResults(null);
    setUploadError(null);

    try {
      const result = await kbList(token);
      const parsed: KBFile[] = result.paths.map((p) => ({
        path: p,
        name: pathToName(p),
        category: formatCategory(pathToCategory(p)),
      }));
      setFiles(parsed);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Erro ao carregar a lista.";
      /* Token expirado ou inválido */
      if (msg.toLowerCase().includes("401") || msg.toLowerCase().includes("não autorizado")) {
        clearToken();
        onLogout();
        return;
      }
      setError(msg);
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
    void doUpload(selected);
    /* Limpa o input para permitir reenvio do mesmo arquivo */
    e.target.value = "";
  }

  async function doUpload(selected: File[]) {
    setUploading(true);
    setUploadResults(null);
    setUploadError(null);

    try {
      const result = await kbUpload(token, selected);
      setUploadResults(result.files);
      /* Recarrega a lista após upload bem-sucedido */
      if (result.ok) {
        await loadFiles();
      }
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Erro durante o upload.");
    } finally {
      setUploading(false);
    }
  }

  /* Abrir arquivo em nova aba */
  function handleOpen(file: KBFile) {
    const url = kbFileUrl(token, file.path);
    window.open(url, "_blank", "noopener,noreferrer");
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
                    <th scope="col" className="kbe-col-date">Tipo</th>
                    <th scope="col" className="kbe-col-actions">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => {
                    const ext = file.path.split(".").pop()?.toUpperCase() ?? "–";
                    return (
                      <tr key={file.path}>
                        <td className="kbe-col-name">
                          <div className="kbe-file-name">{file.name.replace(/-/g, " ")}</div>
                          <div className="kbe-file-path">{file.path}</div>
                        </td>
                        <td className="kbe-col-category">
                          <span className="kbe-badge">{file.category}</span>
                        </td>
                        <td className="kbe-col-date" style={{ fontFamily: "monospace", fontSize: 12 }}>
                          {ext}
                        </td>
                        <td className="kbe-col-actions">
                          <div className="kbe-row-actions">
                            {/* Abrir arquivo */}
                            <button
                              type="button"
                              className="kbe-icon-btn"
                              onClick={() => handleOpen(file)}
                              aria-label={`Abrir ${file.name}`}
                              title="Abrir / visualizar"
                            >
                              <Eye size={16} aria-hidden="true" />
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
