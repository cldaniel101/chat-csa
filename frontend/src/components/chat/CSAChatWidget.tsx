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
import { chatCompletion, getAgentUrl, type AgentId } from "../../api/client";
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
};

type CSAChatWidgetProps = {
  agent?: AgentId;
  token?: string | null;
  isAuthenticated?: boolean;
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

export function CSAChatWidget({
  agent = "consumer",
  token = null,
  isAuthenticated = false,
}: CSAChatWidgetProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [healthResult, setHealthResult] = useState<{
    agent: AgentId;
    status: ChatHealth;
  }>({ agent, status: "checking" });
  const [open, setOpen] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const needsAuth = agent === "ingester";
  const canChat = !needsAuth || isAuthenticated;
  const health = healthResult.agent === agent ? healthResult.status : "checking";

  useEffect(() => {
    const controller = new AbortController();
    const url = getAgentUrl(agent).replace(/\/$/, "");

    fetch(`${url}/health`, { signal: controller.signal })
      .then((response) => {
        setHealthResult({ agent, status: response.ok ? "ok" : "off" });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setHealthResult({ agent, status: "off" });
      });

    return () => controller.abort();
  }, [agent]);

  useEffect(() => {
    if (!open) return;

    const frame = window.requestAnimationFrame(() => {
      messagesRef.current?.scrollTo({
        top: messagesRef.current.scrollHeight,
        behavior: "smooth",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [messages, loading, open]);

  const sendMessage = useCallback(
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt || loading || !canChat) return;

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content: prompt,
        createdAt: new Date(),
      };
      const nextMessages = [...messages, userMessage];

      setMessages(nextMessages);
      setLoading(true);

      try {
        const reply = await chatCompletion(
          agent,
          nextMessages.map(({ role, content }) => ({ role, content })),
          { token: needsAuth ? token : null },
        );

        setMessages([
          ...nextMessages,
          {
            id: generateId(),
            role: "assistant",
            content: reply || "Não foi possível obter uma resposta.",
            createdAt: new Date(),
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
        setLoading(false);
      }
    },
    [agent, canChat, loading, messages, needsAuth, token],
  );

  const runtime = useExternalStoreRuntime<ChatMessage>({
    messages,
    isRunning: loading,
    isDisabled: !canChat,
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
      if (!prompt.trim() || loading || !canChat) return;
      setInput("");
      runtime.threads.main.append(prompt);
    },
    [canChat, loading, runtime],
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

          {!canChat && (
            <div className="csa-chat-auth-message" role="alert">
              Este agente exige autenticação. <a href="/login">Entrar como administrador</a>.
            </div>
          )}

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
                {canChat && (
                  <ChatSuggestions onSelect={submitPrompt} disabled={loading} />
                )}
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
                  <MarkdownMessage content={message.content} />
                ) : (
                  message.content
                )}
              </article>
            ))}

            {loading && <ChatStatus />}
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
              placeholder={
                canChat ? "Digite sua pergunta..." : "Entre para conversar com este agente"
              }
              disabled={!canChat || loading}
            />
            <button
              type="submit"
              className="csa-chat-send"
              disabled={!input.trim() || loading || !canChat}
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
