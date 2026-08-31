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