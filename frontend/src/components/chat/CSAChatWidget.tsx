import {
  AssistantModalPrimitive,
  AssistantRuntimeProvider,
  generateId,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import type { AppendMessage } from "@assistant-ui/react";
import { BsStars } from "react-icons/bs";
import { ChevronDown, Send } from "lucide-react";
import {
  Children,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatCompletionStream, getConsumerUrl, type AgentToolStep } from "../../api/client";
import { ChatHeader, type ChatHealth } from "./ChatHeader";
import { ChatStatus } from "./ChatStatus";
import { ChatSuggestions } from "./ChatSuggestions";
import "./CSAChatWidget.css";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: Date;
  isError?: boolean;
  activity?: AgentActivity;
};

type AgentActivity = {
  reasoning: string;
  steps: AgentToolStep[];
};

type CSAChatWidgetProps = {
  embedded?: boolean;
};

type SourceEntry = {
  id: string;
  text: string;
};

function getTextContent(message: AppendMessage) {
  return message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

const CITATION_PATTERN = /\[(\d+)\]/g;
const SOURCES_HEADING_PATTERN =
  /(?:^|\n)\s*(?:#{1,6}\s*)?(?:\*\*|__)?fontes?\s*:(?:\*\*|__)?/i;
const OFFICIAL_NOTICE_PATTERN =
  /\s*(Em caso de diverg[êe]ncia,\s+prevalece o edital oficial\.?)\s*$/i;
const SOURCE_ENTRY_PATTERN = /\[(\d+)\]\s*([\s\S]*?)(?=\s*\[\d+\]\s|$)/g;

function renderCitationText(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CITATION_PATTERN)) {
    const index = match.index ?? 0;
    const label = match[0];

    if (index > lastIndex) {
      parts.push(text.slice(lastIndex, index));
    }

    parts.push(
      <sup className="csa-chat-citation" key={`${label}-${index}`}>
        {label}
      </sup>,
    );
    lastIndex = index + label.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

function renderMarkdownChildren(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      return renderCitationText(child);
    }

    return child;
  });
}

function splitMessageSections(content: string) {
  const match = SOURCES_HEADING_PATTERN.exec(content);

  if (!match) {
    return { answer: content.trim(), sources: "" };
  }

  return {
    answer: content.slice(0, match.index).trim(),
    sources: content.slice(match.index + match[0].length).trim(),
  };
}

function splitSourcesNotice(sources: string) {
  const match = OFFICIAL_NOTICE_PATTERN.exec(sources);

  if (!match) {
    return { references: sources.trim(), notice: "" };
  }

  return {
    references: sources.slice(0, match.index).trim(),
    notice: match[1].trim(),
  };
}

function parseSourceEntries(sources: string): SourceEntry[] {
  return Array.from(sources.matchAll(SOURCE_ENTRY_PATTERN), (match) => ({
    id: match[1],
    text: match[2].trim(),
  })).filter((entry) => entry.text.length > 0);
}

const markdownComponents = {
  a: ({ children, href }: { children?: ReactNode; href?: string }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p>{renderMarkdownChildren(children)}</p>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li>{renderMarkdownChildren(children)}</li>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong>{renderMarkdownChildren(children)}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => (
    <em>{renderMarkdownChildren(children)}</em>
  ),
};

function SourcesBlock({ content }: { content: string }) {
  const { references, notice } = splitSourcesNotice(content);
  const entries = parseSourceEntries(references);

  if (!references && !notice) {
    return null;
  }

  return (
    <section className="csa-chat-sources" aria-label="Fontes consultadas">
      {references && <h4>Fontes</h4>}
      {entries.length > 0 ? (
        <div className="csa-chat-source-list">
          {entries.map((entry) => (
            <div className="csa-chat-source-item" key={entry.id}>
              <sup className="csa-chat-source-index">[{entry.id}]</sup>
              <div className="csa-chat-source-copy">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {entry.text}
                </ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="csa-chat-source-copy">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {references}
          </ReactMarkdown>
        </div>
      )}
      {notice && <p className="csa-chat-sources-note">{notice}</p>}
    </section>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  const { answer, sources } = splitMessageSections(content);

  return (
    <>
      {answer && (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {answer}
        </ReactMarkdown>
      )}
      {sources && <SourcesBlock content={sources} />}
    </>
  );
}

// ── Atividade do agente: reasoning + passos de ferramenta ────────────────────
const TOOL_DESCRIPTION: Record<string, { icon: string; label: string }> = {
  read: { icon: "📖", label: "Lendo documento" },
  write: { icon: "✏️", label: "Escrevendo arquivo" },
  edit: { icon: "✏️", label: "Editando arquivo" },
  bash: { icon: "💻", label: "Executando comando" },
  web_csa_fetch: { icon: "🌐", label: "Acessando página do portal" },
  web_csa_search: { icon: "🔍", label: "Buscando no portal" },
};

function toolDetail(step: {
  name: string;
  args?: Record<string, unknown>;
}): string {
  const args = step.args ?? {};
  switch (step.name) {
    case "read":
      return typeof args.path === "string" ? args.path : "";
    case "web_csa_fetch":
      return typeof args.url === "string" ? args.url : "";
    case "web_csa_search":
      return typeof args.query === "string" ? args.query : "";
    default:
      return JSON.stringify(args);
  }
}

function describeStep(step: AgentToolStep): string {
  const { icon, label } = TOOL_DESCRIPTION[step.name] ?? {
    icon: "🛠️",
    label: step.name,
  };
  const detail = toolDetail(step);
  return detail ? `${icon} ${label} — ${detail}` : `${icon} ${label}`;
}

function currentStepStatus(steps: AgentToolStep[], reasoning: string): string {
  const openIds = new Set(
    steps.filter((step) => step.type === "tool_start").map((step) => step.id),
  );
  for (const step of steps) {
    if (step.type === "tool_end") openIds.delete(step.id);
  }
  const running = steps
    .filter((step) => step.type === "tool_start" && openIds.has(step.id))
    .at(-1);
  if (running) return `${describeStep(running)}…`;
  if (steps.length > 0) return describeStep(steps[steps.length - 1]);
  if (reasoning) return "💭 Pensando…";
  return "Buscando uma resposta…";
}

function groupToolSteps(steps: AgentToolStep[]) {
  const groups: {
    id: string;
    name: string;
    args?: Record<string, unknown>;
    error: boolean;
  }[] = [];
  const byId = new Map<string, (typeof groups)[number]>();
  for (const step of steps) {
    if (step.type === "tool_start") {
      const group = { id: step.id, name: step.name, args: step.args, error: false };
      byId.set(step.id, group);
      groups.push(group);
    } else {
      const group = byId.get(step.id);
      if (group) group.error = Boolean(step.error);
    }
  }
  return groups;
}

function ActivityBlock({ activity }: { activity: AgentActivity }) {
  const reasoning = activity.reasoning.trim();
  const steps = groupToolSteps(activity.steps);

  if (!reasoning && steps.length === 0) {
    return null;
  }

  return (
    <details className="csa-chat-activity">
      <summary>💭 Atividade do agente</summary>
      {reasoning && (
        <div className="csa-chat-activity-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {reasoning}
          </ReactMarkdown>
        </div>
      )}
      {steps.length > 0 && (
        <ol className="csa-chat-activity-steps">
          {steps.map((step) => {
            const { icon, label } = TOOL_DESCRIPTION[step.name] ?? {
              icon: "🛠️",
              label: step.name,
            };
            const detail = toolDetail(step);
            return (
              <li key={step.id}>
                {icon} <strong>{label}</strong>
                {detail ? ` — ${detail}` : ""}{" "}
                {step.error ? "⚠️ falhou" : "✓"}
              </li>
            );
          })}
        </ol>
      )}
    </details>
  );
}

export function CSAChatWidget({ embedded = false }: CSAChatWidgetProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Mensagem "ao vivo" durante o streaming: conteúdo parcial + status do passo atual.
  const [live, setLive] = useState<{ content: string } | null>(null);
  const [liveSteps, setLiveSteps] = useState<AgentToolStep[]>([]);
  const [liveReasoning, setLiveReasoning] = useState("");
  const reasoningRef = useRef("");
  const stepsRef = useRef<AgentToolStep[]>([]);
  const [health, setHealth] = useState<ChatHealth>("checking");
  const [open, setOpen] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!embedded || window.parent === window) return;

    window.parent.postMessage(
      {
        source: "chat-csa",
        type: "csa-chat:state",
        open,
      },
      "*",
    );
  }, [embedded, open]);

  useEffect(() => {
    const controller = new AbortController();
    const url = getConsumerUrl().replace(/\/$/, "");

    fetch(`${url}/health`, { signal: controller.signal })
      .then((response) => {
        setHealth(response.ok ? "ok" : "off");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setHealth("off");
      });

    return () => controller.abort();
  }, []);

  // nova mensagem (user ou assistant finalizada): sempre leva pro fim
  useEffect(() => {
    if (!open) return;
    const el = messagesRef.current;
    if (!el) return;
    const frame = window.requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, open]);

  // durante o streaming: segue o tamanho da mensagem só se o usuário já
  // estiver perto do fim — um scroll pra cima pausa o acompanhamento
  useEffect(() => {
    if (!open || !live) return;
    const el = messagesRef.current;
    if (!el) return;
    const frame = window.requestAnimationFrame(() => {
      const isNearBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight < 180;
      if (!isNearBottom) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [live, open]);

  const sendMessage = useCallback(
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt || loading) return;

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content: prompt,
        createdAt: new Date(),
      };
      const nextMessages = [...messages, userMessage];

      setMessages(nextMessages);
      setLoading(true);
      reasoningRef.current = "";
      stepsRef.current = [];
      setLiveReasoning("");
      setLiveSteps([]);
      setLive({ content: "" });

      try {
        const reply = await chatCompletionStream(
          nextMessages.map(({ role, content }) => ({ role, content })),
          {
            onReasoning: (delta) => {
              reasoningRef.current += delta;
              setLiveReasoning(reasoningRef.current);
            },
            onToolCall: (step) => {
              stepsRef.current = [...stepsRef.current, step];
              setLiveSteps(stepsRef.current);
            },
            onContent: (delta) => {
              setLive((current) =>
                current ? { content: current.content + delta } : current,
              );
            },
          },
        );

        setMessages([
          ...nextMessages,
          {
            id: generateId(),
            role: "assistant",
            content: reply || "Não foi possível obter uma resposta.",
            createdAt: new Date(),
            activity: {
              reasoning: reasoningRef.current,
              steps: stepsRef.current,
            },
          },
        ]);
      } catch (error: unknown) {
        const errorMessage =
          error instanceof Error ? error.message : "Não foi possível enviar a pergunta.";

        setMessages([
          ...nextMessages,
          {
            id: generateId(),
            role: "assistant",
            content: errorMessage,
            createdAt: new Date(),
            isError: true,
          },
        ]);
      } finally {
        setLive(null);
        setLoading(false);
      }
    },
    [loading, messages],
  );

  const runtime = useExternalStoreRuntime<ChatMessage>({
    messages,
    isRunning: loading,
    isDisabled: false,
    convertMessage: (message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      createdAt: message.createdAt,
    }),
    onNew: async (message) => {
      await sendMessage(getTextContent(message));
    },
  });

  const submitPrompt = useCallback(
    (prompt: string) => {
      if (!prompt.trim() || loading) return;
      setInput("");
      runtime.threads.main.append(prompt);
    },
    [loading, runtime],
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitPrompt(input);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitPrompt(input);
    }
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AssistantModalPrimitive.Root
        open={open}
        onOpenChange={setOpen}
        unstable_openOnRunStart
      >
        <AssistantModalPrimitive.Anchor asChild>
          <div className="csa-chat-anchor">
            <AssistantModalPrimitive.Trigger asChild>
              <button
                type="button"
                className="csa-chat-launcher"
                aria-label={open ? "Minimizar Assistente CSA" : "Abrir Assistente CSA"}
                aria-expanded={open}
              >
                <BsStars
                  className={`csa-chat-launcher-icon ${open ? "is-hidden" : ""}`}
                  size={27}
                  aria-hidden="true"
                />
                <ChevronDown
                  className={`csa-chat-launcher-icon ${open ? "" : "is-hidden"}`}
                  size={28}
                  aria-hidden="true"
                />
              </button>
            </AssistantModalPrimitive.Trigger>
          </div>
        </AssistantModalPrimitive.Anchor>

        <AssistantModalPrimitive.Content
          side="top"
          align="end"
          sideOffset={12}
          className="csa-chat-panel"
          role="dialog"
          aria-labelledby="csa-chat-title"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
        >
          <ChatHeader
            health={health}
            canClear={messages.length > 0 && !loading}
            onClear={() => setMessages([])}
            onClose={() => setOpen(false)}
          />

          <div
            className="csa-chat-messages"
            ref={messagesRef}
            aria-label="Histórico da conversa"
          >
            {messages.length === 0 && (
              <div className="csa-chat-welcome">
                <div className="csa-chat-welcome-icon" aria-hidden="true">
                  <BsStars size={26} />
                </div>
                <h3>
                  Olá! <span aria-hidden="true">👋</span>
                </h3>
                <p>Sou o assistente do processo seletivo da UEFS.</p>
                <p>Como posso ajudar?</p>
                <ChatSuggestions onSelect={submitPrompt} disabled={loading} />
              </div>
            )}

            {messages.map((message) => (
              <article
                key={message.id}
                className={`csa-chat-message csa-chat-message--${message.role}${
                  message.isError ? " csa-chat-message--error" : ""
                }`}
                aria-label={message.role === "user" ? "Você" : "Assistente CSA"}
                role={message.isError ? "alert" : undefined}
              >
                {message.role === "assistant" ? (
                  <>
                    {message.activity && <ActivityBlock activity={message.activity} />}
                    <MarkdownMessage content={message.content} />
                  </>
                ) : (
                  message.content
                )}
              </article>
            ))}

            {loading && !live && <ChatStatus />}

            {live && (
              <article
                className="csa-chat-message csa-chat-message--assistant csa-chat-live"
                aria-label="Assistente CSA respondendo"
              >
                {/* Durante o streaming o <details> fica aberto para o reasoning/tool calls
                    não ocuparem o espaço da resposta final — no final vira o ActivityBlock
                    colapsado da mensagem. Estilo markdown, não card. */}
                <details className="csa-chat-activity" open>
                  <summary>💭 Atividade do agente</summary>
                  {liveReasoning ? (
                    <div className="csa-chat-activity-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {liveReasoning}
                      </ReactMarkdown>
                    </div>
                  ) : liveSteps.length === 0 ? (
                    <div className="csa-chat-activity-body csa-chat-activity--muted">
                      <span className="csa-chat-typing" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </span>{" "}
                      {currentStepStatus(liveSteps, liveReasoning)}
                    </div>
                  ) : null}
                  {liveSteps.length > 0 && (
                    <ol className="csa-chat-activity-steps">
                      {groupToolSteps(liveSteps).map((step) => {
                        const { icon, label } = TOOL_DESCRIPTION[step.name] ?? {
                          icon: "🛠️",
                          label: step.name,
                        };
                        const detail = toolDetail(step);
                        return (
                          <li key={step.id}>
                            {icon} <strong>{label}</strong>
                            {detail ? ` — ${detail}` : ""}{" "}
                            {step.error ? "⚠️ falhou" : "✓"}
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </details>
                {live.content !== "" ? (
                  <div className="csa-chat-live-answer">
                    <MarkdownMessage content={live.content} />
                  </div>
                ) : (
                  <div className="csa-chat-status">
                    <span className="csa-chat-typing" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                    <span role="status" aria-live="polite">
                      Gerando resposta…
                    </span>
                  </div>
                )}
              </article>
            )}
          </div>

          <form className="csa-chat-composer" onSubmit={handleSubmit}>
            <label className="csa-sr-only" htmlFor="csa-chat-input">
              Digite sua pergunta
            </label>
            <textarea
              id="csa-chat-input"
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Digite sua pergunta..."
            />
            <button
              type="submit"
              className="csa-chat-send"
              disabled={!input.trim() || loading}
              aria-label="Enviar mensagem"
              title="Enviar mensagem"
            >
              <Send size={20} aria-hidden="true" />
            </button>
            <p className="csa-chat-composer-hint">
              Enter envia <span aria-hidden="true">·</span> Shift+Enter quebra a linha
            </p>
          </form>
        </AssistantModalPrimitive.Content>
      </AssistantModalPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}
