import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { getAgentUrl } from "../api/client";

type User = { id: string; username: string; role: string };

export default function Admin() {
  const { token } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "admin" });
  const [editing, setEditing] = useState<User | null>(null);

  const base = getAgentUrl("ingester").replace(/\/$/, "");

  async function load() {
    setErr(null);
    const res = await fetch(`${base}/admin/users`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      setErr(j.detail || "failed to load users");
      return;
    }
    setUsers(await res.json());
  }

  useEffect(() => {
    if (token) load();
  }, [token]);

  async function create() {
    setErr(null);
    setOk(null);
    if (!form.username || !form.password) return setErr("username and password required");
    const res = await fetch(`${base}/admin/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(form),
    });
    const j = await res.json();
    if (!res.ok) return setErr(j.detail || "create failed");
    setOk(`Created ${j.username}`);
    setForm({ username: "", password: "", role: "admin" });
    load();
  }

  async function saveEdit() {
    if (!editing) return;
    const res = await fetch(`${base}/admin/users/${editing.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ username: editing.username, password: (editing as any).password, role: editing.role }),
    });
    const j = await res.json();
    if (!res.ok) return setErr(j.detail || "update failed");
    setOk("Updated");
    setEditing(null);
    load();
  }

  async function del(id: string) {
    if (!confirm("Delete user?")) return;
    const res = await fetch(`${base}/admin/users/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) return setErr(j.detail || "delete failed");
    setOk("Deleted");
    load();
  }

  if (!token) {
    return (
      <div className="admin">
        <div className="alert err">Not authenticated. <a href="/login">Sign in</a> as admin first.</div>
      </div>
    );
  }

  return (
    <div className="admin">
      <h2 style={{ marginTop: 0 }}>Admin — users</h2>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>Simple CRUD for the ingester adm account. Default: <code>admin / sudo123</code>. Stored in-memory on the ingester API.</p>

      {err && <div className="alert err">{err}</div>}
      {ok && <div className="alert ok">{ok}</div>}

      <div className="inline-form">
        <input placeholder="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input placeholder="password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "8px 10px" }}>
          <option value="admin">admin</option>
          <option value="editor">editor</option>
        </select>
        <button className="btn" onClick={create}>Add</button>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>id</th>
            <th>username</th>
            <th>role</th>
            <th style={{ width: 140 }}></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{u.id}</td>
              <td>
                {editing?.id === u.id ? (
                  <input value={editing.username} onChange={(e) => setEditing({ ...editing, username: e.target.value })} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, padding: "6px 8px" }} />
                ) : (
                  u.username
                )}
              </td>
              <td>
                {editing?.id === u.id ? (
                  <select value={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value })} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, padding: "6px 8px" }}>
                    <option value="admin">admin</option>
                    <option value="editor">editor</option>
                  </select>
                ) : (
                  u.role
                )}
              </td>
              <td style={{ display: "flex", gap: 6 }}>
                {editing?.id === u.id ? (
                  <>
                    <input
                      placeholder="new password (optional)"
                      type="password"
                      onChange={(e) => setEditing({ ...editing, password: e.target.value } as any)}
                      style={{ flex: 1, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, padding: "6px 8px" }}
                    />
                    <button className="btn" onClick={saveEdit}>Save</button>
                    <button className="btn ghost" onClick={() => setEditing(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button className="btn ghost" onClick={() => setEditing(u)}>Edit</button>
                    <button className="btn ghost" onClick={() => del(u.id)}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
