// Cliente da API do agente consumer — o frontend é exclusivo do consumer
// (decisão da discussão ingester-fasthtml-admin): o ingester tem painel
// próprio em FastHTML servido pelo backend, sem auth aqui.

function defaultConsumerUrl(): string {
  if (typeof window === "undefined") {
    return "http://localhost:8002";
  }

  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${window.location.hostname}:8002`;
}

function runtimeConsumerUrl(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  const paramUrl = params.get("consumerUrl")?.trim();
  if (paramUrl) {
    return paramUrl;
  }

  const configuredWindow = window as Window & {
    __CSA_CHAT_CONSUMER_URL__?: string;
  };
  return configuredWindow.__CSA_CHAT_CONSUMER_URL__?.trim() || null;
}

export function getConsumerUrl(): string {
  return runtimeConsumerUrl() || import.meta.env.VITE_CONSUMER_URL || defaultConsumerUrl();
}

function networkErrorMessage(base: string): string {
  return `Não consegui conectar ao agente consumer. Verifique se o backend está rodando em ${base} e tente novamente.`;
}

async function responseErrorMessage(res: Response): Promise<string> {
  const fallback = `O agente respondeu com erro HTTP ${res.status}.`;
  const text = await res.text();

  if (!text) {
    return fallback;
  }

  try {
    const payload = JSON.parse(text);
    return payload?.detail || payload?.error?.message || fallback;
  } catch {
    return text;
  }
}

/** Erro de autenticação (HTTP 401) — o front deve voltar para o login. */
export class UnauthorizedError extends Error {
  constructor(message = "Sessão expirada. Faça login novamente.") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

/** Lança o erro adequado quando a resposta não é 2xx. */
async function ensureOk(res: Response): Promise<void> {
  if (res.ok) {
    return;
  }
  if (res.status === 401) {
    throw new UnauthorizedError();
  }
  throw new Error(await responseErrorMessage(res));
}

export type ChatCompletionMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

// Eventos do rastro do agente enviados pelo backend via `delta` estendido:
// reasoning (thinking do modelo) e tool_call (passos de ferramenta).
export type AgentToolStep = {
  type: "tool_start" | "tool_end";
  id: string;
  name: string;
  args?: Record<string, unknown>;
  error?: boolean;
};

export type StreamHandlers = {
  onReasoning?: (delta: string) => void;
  onToolCall?: (step: AgentToolStep) => void;
  onContent?: (delta: string) => void;
};

type StreamChunk = {
  choices?: Array<{
    delta?: {
      content?: string;
      reasoning?: string;
      tool_call?: AgentToolStep;
      role?: string;
    };
  }>;
  // fallback caso o servidor envie delta no nível raiz
  delta?: {
    content?: string;
    reasoning?: string;
    tool_call?: AgentToolStep;
  };
  error?: { message?: string };
};

/**
 * Envia a conversa com stream:true e roteia cada chunk SSE para os
 * handlers (reasoning/tool_call/content). Retorna o texto final completo.
 */
export async function chatCompletionStream(
  messages: ChatCompletionMessage[],
  handlers: StreamHandlers = {},
): Promise<string> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "chat-csa",
        messages,
        stream: true,
      }),
    });
  } catch {
    throw new Error(networkErrorMessage(base));
  }

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res));
  }
  if (!res.body) {
    throw new Error("O agente não retornou um corpo de streaming.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";

  const handleLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) return;
    const data = trimmed.slice(5).trim();
    if (!data || data === "[DONE]") return;

    let chunk: StreamChunk;
    try {
      chunk = JSON.parse(data);
    } catch {
      return; // ignora linhas não-JSON (keep-alive etc.)
    }

    if (chunk.error?.message) {
      throw new Error(chunk.error.message);
    }

    const delta =
      chunk.choices?.[0]?.delta ?? chunk.delta;
    if (!delta) return;

    if (delta.reasoning) {
      handlers.onReasoning?.(delta.reasoning);
    }
    if (delta.tool_call) {
      handlers.onToolCall?.(delta.tool_call);
    }
    if (delta.content) {
      answer += delta.content;
      handlers.onContent?.(delta.content);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        handleLine(line);
      }
    }
    if (buffer.trim()) {
      handleLine(buffer);
    }
  } catch (error) {
    if (error instanceof Error && error.message) {
      throw error;
    }
    throw new Error("Falha ao ler o streaming do agente.");
  }

  return answer;
}

/** Versão sem streaming (compat): espera a resposta completa. */
export async function chatCompletion(
  messages: ChatCompletionMessage[],
): Promise<string> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "chat-csa",
        messages,
        stream: false,
      }),
    });
  } catch {
    throw new Error(networkErrorMessage(base));
  }

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res));
  }
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "";
}

// ─── Autenticação admin ──────────────────────────────────────────────────────

export type AuthToken = {
  access_token: string;
  token_type: string;
  user: { username: string; role: string };
};

/** Faz login admin e retorna o token de acesso. */
export async function authLogin(
  username: string,
  password: string,
): Promise<AuthToken> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(`${base.replace(/\/$/, "")}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new Error(
      `Não foi possível conectar ao servidor em ${base}. Verifique se o backend está em execução.`,
    );
  }

  if (!res.ok) {
    const fallback = "Usuário ou senha inválidos.";
    const text = await res.text();
    try {
      const payload = JSON.parse(text);
      throw new Error(payload?.detail || payload?.error || fallback);
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(fallback);
      throw e;
    }
  }

  return res.json();
}

// ─── Base de conhecimento (/kb/*) ────────────────────────────────────────────

export type KBListResult = {
  prefix: string;
  paths: string[];
};

export type KBUploadFileResult = {
  path: string;
  ok: boolean;
  size?: number;
  converted?: boolean;
  error?: string;
};

export type KBUploadResult = {
  ok: boolean;
  sha?: string;
  files: KBUploadFileResult[];
  error?: string;
};

/**
 * Lista caminhos disponíveis na base de conhecimento.
 * Requer token admin obtido via `authLogin`.
 */
export async function kbList(
  token: string,
  prefix = "",
): Promise<KBListResult> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(
      `${base.replace(/\/$/, "")}/kb/list?prefix=${encodeURIComponent(prefix)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
  } catch {
    throw new Error(`Não foi possível conectar ao servidor em ${base}.`);
  }

  await ensureOk(res);
  return res.json();
}

export type KBFileResult = {
  blob: Blob;
  contentType: string;
};

/**
 * Baixa o arquivo original da base com o header `Authorization`.
 *
 * O front renderiza o conteúdo (preview), em vez de redirecionar para a API:
 * navegações diretas (`window.open`/`<a href>`) não enviam o header de
 * autorização, o que resultava em 401.
 */
export async function kbFile(token: string, path: string): Promise<KBFileResult> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(
      `${base.replace(/\/$/, "")}/kb/file?path=${encodeURIComponent(path)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
  } catch {
    throw new Error(`Não foi possível conectar ao servidor em ${base}.`);
  }

  await ensureOk(res);

  const blob = await res.blob();
  return {
    blob,
    contentType:
      res.headers.get("content-type") || blob.type || "application/octet-stream",
  };
}

/**
 * Remove um arquivo da base de conhecimento via commit atômico.
 * Exige token admin obtido via `authLogin`.
 */
export async function kbDelete(token: string, path: string): Promise<{ ok: boolean; sha?: string }> {
  const base = getConsumerUrl();
  let res: Response;

  try {
    res = await fetch(
      `${base.replace(/\/$/, "")}/kb/file?path=${encodeURIComponent(path)}`,
      { method: "DELETE", headers: { Authorization: `Bearer ${token}` } },
    );
  } catch {
    throw new Error(`Não foi possível conectar ao servidor em ${base}.`);
  }

  await ensureOk(res);
  return res.json();
}

export type KBUploadOptions = {
  /** Seção (pasta) de destino; o servidor exige ao menos uma. Ex.: "editais". */
  section?: string;
  /** Mensagem do commit (opcional). */
  message?: string;
};

/**
 * Faz upload de um lote de arquivos para a base de conhecimento.
 * `files` é uma lista de File (selecionados via <input type="file">).
 *
 * O servidor exige que o caminho declarado tenha uma pasta de seção
 * (`<seção>/<arquivo>`), que vai no filename da parte multipart.
 */
export async function kbUpload(
  token: string,
  files: File[],
  options: KBUploadOptions = {},
): Promise<KBUploadResult> {
  const base = getConsumerUrl();
  const formData = new FormData();
  const section = (options.section ?? "")
    .trim()
    .replace(/^\/+|\/+$/g, "")
    .replace(/\\/g, "/");

  for (const file of files) {
    const declared = section ? `${section}/${file.name}` : file.name;
    formData.append("files", file, declared);
  }

  if (options.message) {
    formData.append("message", options.message);
  }

  let res: Response;
  try {
    res = await fetch(`${base.replace(/\/$/, "")}/kb/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
  } catch {
    throw new Error(`Não foi possível conectar ao servidor em ${base}.`);
  }

  await ensureOk(res);
  return res.json();
}
