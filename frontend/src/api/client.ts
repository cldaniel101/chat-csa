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

export function getConsumerUrl(): string {
  return import.meta.env.VITE_CONSUMER_URL || defaultConsumerUrl();
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