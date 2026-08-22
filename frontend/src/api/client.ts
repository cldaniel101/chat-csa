export type AgentId = "ingester" | "consumer";

export function getAgentUrl(agent: AgentId): string {
  if (agent === "ingester") {
    return import.meta.env.VITE_INGESTER_URL || "http://localhost:8001";
  }
  return import.meta.env.VITE_CONSUMER_URL || "http://localhost:8002";
}

export async function chatCompletion(
  agent: AgentId,
  messages: { role: "user" | "assistant" | "system"; content: string }[],
  opts?: { token?: string | null; signal?: AbortSignal }
): Promise<string> {
  const base = getAgentUrl(agent);
  const res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
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
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
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
  const res = await fetch(`${base.replace(/\/$/, "")}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(opts?.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: JSON.stringify({ model: "chat-csa", messages, stream: true }),
    signal: opts?.signal,
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
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
