export type AgentId = "ingester" | "consumer";

function defaultAgentUrl(port: number): string {
  if (typeof window === "undefined") {
    return `http://localhost:${port}`;
  }

  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${window.location.hostname}:${port}`;
}

export function getAgentUrl(agent: AgentId): string {
  if (agent === "ingester") {
    return import.meta.env.VITE_INGESTER_URL || defaultAgentUrl(8001);
  }
  return import.meta.env.VITE_CONSUMER_URL || defaultAgentUrl(8002);
}

function networkErrorMessage(agent: AgentId, base: string): string {
  const label = agent === "consumer" ? "consumer" : "ingester";
  return `Não consegui conectar ao agente ${label}. Verifique se o backend está rodando em ${base} e tente novamente.`;
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

export async function chatCompletion(
  agent: AgentId,
  messages: { role: "user" | "assistant" | "system"; content: string }[],
  opts?: { token?: string | null; signal?: AbortSignal }
): Promise<string> {
  const base = getAgentUrl(agent);
  let res: Response;

  try {
    res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(opts?.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      },
      body: JSON.stringify({
        model: "chat-csa",
        messages,
        stream: false,
      }),
      signal: opts?.signal,
    });
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new Error(networkErrorMessage(agent, base));
  }

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res));
  }
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "";
}

export async function chatCompletionStream(
  agent: AgentId,
  messages: { role: string; content: string }[],
  onChunk: (chunk: string) => void,
  opts?: { token?: string | null; signal?: AbortSignal }
) {
  const base = getAgentUrl(agent);
  let res: Response;

  try {
    res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(opts?.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      },
      body: JSON.stringify({ model: "chat-csa", messages, stream: true }),
      signal: opts?.signal,
    });
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new Error(networkErrorMessage(agent, base));
  }

  if (!res.ok || !res.body) {
    throw new Error(await responseErrorMessage(res));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        const j = JSON.parse(data);
        const delta = j.choices?.[0]?.delta?.content;
        if (delta) onChunk(delta);
      } catch {}
    }
  }
}
