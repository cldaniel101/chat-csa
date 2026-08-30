import { BrowserRouter, Routes, Route, Link, useLocation, useSearchParams, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Chat from "./components/Chat";
import Login from "./components/Login";
import Admin from "./components/Admin";
import "./App.css";

function Sidebar() {
  const [search, setSearch] = useSearchParams();
  const agent = (search.get("agent") as "ingester" | "consumer") || "consumer";
  const { isAuthenticated, user, logout } = useAuth();
  const needsAuth = agent === "ingester";

  return (
    <aside className="sidebar">
      <h3>Agents</h3>

      <div className={`agent-card ${agent === "consumer" ? "active" : ""}`} onClick={() => setSearch({ agent: "consumer" })}>
        <h4>Consumer</h4>
        <p>Public chat. Answers with citations from the curated bundle.</p>
        <span className="status"><span className="dot" /> port {import.meta.env.VITE_CONSUMER_URL || "8002"} · no login</span>
      </div>

      <div className={`agent-card ${agent === "ingester" ? "active" : ""}`} onClick={() => setSearch({ agent: "ingester" })}>
        <h4>Ingester</h4>
        <p>Curation agent. Crawls & normalizes CSA sources into OKF.</p>
        <span className="status"><span className={`dot ${isAuthenticated ? "" : "off"}`} /> {isAuthenticated ? `as ${user?.username}` : "login required"}</span>
      </div>

      <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
        {needsAuth && !isAuthenticated && <Link to="/login" className="btn" style={{ textAlign: "center" }}>Sign in to ingester</Link>}
        {isAuthenticated && <button className="btn ghost" onClick={logout}>Sign out {user?.username}</button>}
        <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
          Skills live in <code>.ingester/skills/</code> & <code>.consumer/skills/</code> + <code>AGENTS.md</code>. Hot-reloaded each request.
        </div>
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link to="/chat?agent=consumer" className="pill">Chat</Link>
          <Link to="/admin" className="pill">Admin</Link>
          <Link to="/login" className="pill">Login</Link>
        </nav>
      </div>
    </aside>
  );
}

function Layout() {
  const location = useLocation();
  const isChat = location.pathname.startsWith("/chat") || location.pathname === "/";
  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <Link to="/chat?agent=consumer" className="brand" style={{ color: "inherit" }}>
            <span className="brand-badge">CSA</span>
            Chat CSA
            <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 12, marginLeft: 4 }}>SISU/UEFS · ingester + consumer</span>
          </Link>
          <nav className="nav">
            <Link to="/chat?agent=consumer" className="pill">Chat</Link>
            <Link to="/chat?agent=ingester" className="pill">Ingester</Link>
            <Link to="/admin" className="pill">Admin</Link>
          </nav>
        </div>
      </header>

      {isChat ? (
        <main className="main">
          <Sidebar />
          <Routes>
            <Route path="/" element={<Navigate to="/chat?agent=consumer" replace />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </main>
      ) : (
        <main style={{ maxWidth: 1100, margin: "0 auto", padding: 16, width: "100%" }}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="*" element={<Navigate to="/chat?agent=consumer" replace />} />
          </Routes>
        </main>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Layout />
      </AuthProvider>
    </BrowserRouter>
  );
}
