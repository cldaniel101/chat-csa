import { createContext, useContext, useEffect, useState } from "react";

type User = { id: string; username: string; role: string };

type AuthState = {
  token: string | null;
  user: User | null;
  login: (username: string, password: string, ingesterUrl: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
};

const AuthContext = createContext<AuthState>(null as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("csa_token"));
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem("csa_user");
    return raw ? JSON.parse(raw) : null;
  });

  useEffect(() => {
    if (token) localStorage.setItem("csa_token", token);
    else localStorage.removeItem("csa_token");
  }, [token]);
  useEffect(() => {
    if (user) localStorage.setItem("csa_user", JSON.stringify(user));
    else localStorage.removeItem("csa_user");
  }, [user]);

  async function login(username: string, password: string, ingesterUrl: string) {
    const url = `${ingesterUrl.replace(/\/$/, "")}/auth/login`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || "Login failed");
    }
    const data = await res.json();
    setToken(data.access_token);
    setUser(data.user);
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ token, user, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
