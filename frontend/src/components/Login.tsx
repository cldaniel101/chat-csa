import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getAgentUrl } from "../api/client";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("sudo123");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      await login(username, password, getAgentUrl("ingester"));
      nav("/chat?agent=ingester");
    } catch (e: any) {
      setErr(e.message || "invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center">
      <form className="card" onSubmit={onSubmit}>
        <h1>Ingester login</h1>
        <p>Restricted area. Use the admin account to access the ingester agent.</p>
        {err && <div className="alert err">{err}</div>}
        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" autoComplete="username" />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="sudo123" autoComplete="current-password" />
        </div>
        <button className="btn" style={{ width: "100%" }} disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
        <div style={{ marginTop: 12, fontSize: 12, color: "var(--muted)", textAlign: "center" }}>
          Default: <code>admin / sudo123</code> — manage in <a href="/admin">Admin</a>
        </div>
      </form>
    </div>
  );
}
