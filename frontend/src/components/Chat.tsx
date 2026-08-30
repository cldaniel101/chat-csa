import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams, Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { chatCompletion } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { AgentId } from "../api/client";
import { getAgentUrl } from "../api/client";

type Msg = { role: "user" | "assistant"; content: string };

function MarkdownMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children, href }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function Chat() {
  const [search, setSearch] = useSearchParams();
  const agent = (search.get("agent") as AgentId) || "consumer";
  const { token, isAuthenticated } = useAuth();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<"ok" | "off" | "checking">("checking");
  const listRef = useRef<HTMLDivElement>(null);

  const needsAuth = agent === "ingester";
  const canChat = !needsAuth || isAuthenticated;

  useEffect(() => {
    const url = getAgentUrl(agent);
    setHealth("checking");
    fetch(`${url.replace(/\/$/, "")}/health`)
      .then((r) => (r.ok ? setHealth("ok") : setHealth("off")))
      .catch(() => setHealth("off"));
  }, [agent]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 999999, behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    const next: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const reply = await chatCompletion(agent, next as any, { token: needsAuth ? token : null });
      setMessages([...next, { role: "assistant", content: reply || "(empty)" }]);
    } catch (e: any) {
      setMessages([...next, { role: "assistant", content: `⚠️ ${e.message || "request failed. Is the agent running?"}` }]);
    } finally {
      setLoading(false);
    }
  }

  function switchAgent(next: AgentId) {
    setSearch({ agent: next });
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <div>
          <h2>{agent === "ingester" ? "Ingester" : "Consumer"} — Chat</h2>
          <span>
            {agent === "ingester" ? "Curates CSA sources → OKF bundle" : "Answers with citations"} ·{" "}
            <span className="status">
              <span className={`dot ${health === "ok" ? "" : "off"}`} /> {health === "ok" ? "online" : health === "checking" ? "checking…" : "offline"}
            </span>
          </span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn ghost" onClick={() => setMessages([])}>Clear</button>
        </div>
      </div>

      {!canChat && (
        <div style={{ padding: 12 }}>
          <div className="alert err">
            Ingester is protected. <Link to="/login">Sign in as admin</Link> to chat with the ingester agent.
          </div>
        </div>
      )}

      <div className="messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="bubble meta">
            {canChat ? `Start chatting with ${agent}. Try: “quais documentos para matrícula?”` : `Sign in to chat with ingester`}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role === "user" ? "user" : "bot"}`}>
            {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : m.content}
          </div>
        ))}
        {loading && <div className="bubble bot">…</div>}
      </div>

      <div className="input-bar">
        <input
          placeholder={
            !canChat
              ? "Sign in to chat with ingester"
              : agent === "ingester"
                ? "Ask to ingest / curate — e.g. 'ingest edital…'"
                : "Ask about SISU/UEFS — e.g. 'quando sai o resultado?'"
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={!canChat}
        />
        <button className="btn" onClick={send} disabled={loading || !canChat || !input.trim()}>
          Send
        </button>
      </div>

      {/* o seletor de agente fica na sidebar, mas também é exposto aqui para mobile */}
      <div style={{ display: "none" }}>
        <button onClick={() => switchAgent("ingester")}></button>
      </div>
    </div>
  );
}
