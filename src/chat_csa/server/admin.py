"""Painel admin do ingester — páginas FastHTML servidas pelo próprio servidor.

Decisão da discussão `ingester-fasthtml-admin` (proposta v1 aceita):
o ingester sai do frontend React compartilhado e vira uma página FastHTML
em `/admin`, barrada por tela de login com sessão por cookie. O token
continua o mesmo do `auth_store` (em memória), agora carregado em cookie
HttpOnly em vez de header Bearer no frontend.

Rotas (montadas sob `/admin`):
  GET  /admin        → página de login ou painel, conforme a sessão
  POST /admin/login  → valida credenciais e abre a sessão
  POST /admin/logout → encerra a sessão
"""

from __future__ import annotations

import os

from fasthtml.common import (
    H1,
    Button,
    Div,
    FastHTML,
    Form,
    Input,
    Label,
    P,
    RedirectResponse,
    Script,
    Style,
    Textarea,
    Title,
)
from starlette.requests import Request

from . import auth as auth_store

# Cookie de sessão do painel (valor = token do auth_store, em memória)
_SESSION_COOKIE = "csa_admin_token"
# HttpOnly + SameSite=Lax; Secure ativado via env para deps atrás de https (ex.: Vercel)
_COOKIE_SECURE = os.getenv("ADMIN_COOKIE_SECURE", "0") == "1"

# Tokens visuais herdados do widget do consumer (frontend/src/components/chat/CSAChatWidget.css)
_BRAND_CSS = """
    :root { --csa-primary: #A11284; --csa-accent: #EE5983; --csa-bg: #F5F5F5; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: "Open Sans", Georgia, Verdana, sans-serif;
           background: var(--csa-bg); color: #191919; }
    .login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #fff; border-radius: 14px; box-shadow: 0 12px 36px rgba(25,25,25,.18);
            width: 380px; max-width: 92vw; padding: 28px; }
    .brand { font-size: 20px; font-weight: 700; color: var(--csa-primary); margin: 0 0 4px; }
    .sub { color: #666; font-size: 13px; margin: 0 0 20px; }
    label { display: block; font-size: 13px; font-weight: 600; color: #333; margin: 12px 0 4px; }
    input { width: 100%; padding: 10px 12px; font-size: 14px; border: 1px solid rgba(238,89,131,.48);
            border-radius: 6px; }
    input:focus { outline: 2px solid var(--csa-accent); border-color: var(--csa-accent); }
    .btn { width: 100%; margin-top: 18px; padding: 11px; font-size: 14px; font-weight: 600;
           color: #fff; background: var(--csa-primary); border: 0; border-radius: 6px; cursor: pointer; }
    .btn:hover { background: #8b0f72; }
    .error { background: #fdecea; color: #b3261e; border: 1px solid #f5c6c0; border-radius: 6px;
             padding: 10px 12px; font-size: 13px; margin-top: 14px; }
    .hint { color: #999; font-size: 12px; text-align: center; margin-top: 16px; }

    /* Painel / chat do ingester */
    .topbar { background: var(--csa-primary); color: #fff; padding: 14px 20px;
              display: flex; align-items: center; justify-content: space-between; }
    .topbar .title { font-size: 16px; font-weight: 700; }
    .topbar .sub { color: rgba(255,255,255,.85); font-size: 12px; margin: 0; }
    .topbar form { margin: 0; }
    .logout { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,.6);
              border-radius: 9999px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
    .logout:hover { background: rgba(255,255,255,.15); }
    .chat-wrap { max-width: 760px; margin: 0 auto; padding: 20px; display: flex;
                 flex-direction: column; height: calc(100vh - 61px); }
    .thread { flex: 1; overflow-y: auto; padding: 8px 4px 16px; display: flex;
              flex-direction: column; gap: 10px; }
    .bubble { max-width: 82%; padding: 10px 14px; border-radius: 12px; font-size: 14px;
              line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
    .bubble p { margin: 0 0 8px; } .bubble p:last-child { margin-bottom: 0; }
    .bubble ul, .bubble ol { margin: 0 0 8px; padding-left: 20px; }
    .bubble li { margin-bottom: 2px; }
    .bubble pre { background: #f0f0f0; border-radius: 6px; padding: 10px; overflow-x: auto;
                  font-size: 12.5px; } .bubble code { background: #f0f0f0; border-radius: 4px;
                  padding: 1px 5px; font-size: 12.5px; } .bubble pre code { padding: 0; }
    .bubble h3, .bubble h4 { margin: 10px 0 6px; font-size: 15px; }
    .bubble a { color: var(--csa-primary); }
    .bubble--user { align-self: flex-end; background: var(--csa-accent); color: #fff;
                    border-bottom-right-radius: 4px; }
    .bubble--assistant { align-self: flex-start; background: #fff; color: #191919;
                         border: 1px solid #eee; border-bottom-left-radius: 4px; }
    .bubble--error { align-self: flex-start; background: #fdecea; color: #b3261e;
                     border: 1px solid #f5c6c0; }
    .typing { color: #999; font-style: italic; font-size: 13px; }
    .composer { display: flex; gap: 10px; background: #fff; border: 1px solid rgba(238,89,131,.48);
                border-radius: 10px; padding: 10px; }
    .composer textarea { flex: 1; border: 0; resize: none; font: inherit; font-size: 14px;
                         outline: none; max-height: 140px; }
    .composer button { border: 0; background: var(--csa-primary); color: #fff; font-weight: 600;
                       border-radius: 8px; padding: 0 18px; cursor: pointer; font-size: 14px; }
    .composer button:disabled { opacity: .5; cursor: default; }
    .hint { color: #999; font-size: 12px; text-align: center; margin: 8px 0 0; }
    .empty { color: #888; text-align: center; margin: auto; font-size: 14px; }
    """


def _get_user(request: Request) -> dict | None:
    """Devolve o usuário da sessão (cookie) ou None."""
    token = request.cookies.get(_SESSION_COOKIE)
    return auth_store.verify_token(token)


def _login_page(error: str = "") -> tuple:
    """Página de login do painel."""
    error_box = Div(error, cls="error") if error else ""
    return (
        Title("Assistente CSA — Acesso restrito"),
        Style(_BRAND_CSS),
        Div(
            Div(
                P("✦✦", style="color: var(--csa-accent); font-size: 26px; margin: 0 0 6px;"),
                H1("Painel do ingester", cls="brand"),
                P("Assistente CSA — acesso restrito ao agente de ingestão.", cls="sub"),
                Form(
                    Label("Usuário", _for="username"),
                    Input(id="username", name="username", type="text", autocomplete="username", required=True),
                    Label("Senha", _for="password"),
                    Input(id="password", name="password", type="password", autocomplete="current-password", required=True),
                    Button("Entrar", type="submit", cls="btn"),
                    error_box,
                    method="post",
                    action="/admin/login",
                ),
                P("Use a conta de administrador do servidor.", cls="hint"),
                cls="card",
            ),
            cls="login-wrap",
        ),
    )


# Chat do painel: mesmo protocolo SSE do widget do consumer (frontend/src/api/client.ts) —
# POST /v1/chat/completions com stream:true, deltas em choices[0].delta.content.
# Histórico fica no cliente; o servidor é stateless por request.
_CHAT_JS = r"""
(() => {
  const thread = document.getElementById('thread');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const history = [];
  let busy = false;

  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Renderização mínima de markdown (sem dependências externas)
  const renderMarkdown = (src) => {
    const inline = (s) => s
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    const out = [];
    let inCode = false, codeBuf = [];
    for (const raw of esc(src).split('\n')) {
      const line = raw.replace(/\s+$/, '');
      if (line.trim().startsWith('```')) {
        if (inCode) { out.push('<pre>' + codeBuf.join('\n') + '</pre>'); codeBuf = []; }
        inCode = !inCode; continue;
      }
      if (inCode) { codeBuf.push(line); continue; }
      const h = line.match(/^#{1,6}\s/);
      if (h) {
        const lvl = Math.min(h[0].length - 1 + 2, 4);
        out.push('<h' + lvl + '>' + inline(line.replace(/^#{1,6}\s*/, '')) + '</h' + lvl + '>');
      } else if (/^\s*[-*]\s/.test(line)) {
        out.push('<li>' + inline(line.replace(/^\s*[-*]\s/, '')) + '</li>');
      } else if (!line.trim()) {
        out.push('<p></p>');
      } else {
        out.push('<p>' + inline(line) + '</p>');
      }
    }
    return out.join('');
  };

  const bubble = (role, content) => {
    const el = document.createElement('div');
    el.className = 'bubble bubble--' + role;
    el.innerHTML = content;
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  };

  const emptyNote = thread.querySelector('.empty');
  if (emptyNote) emptyNote.remove();

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    sendBtn.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    history.push({ role: 'user', content: text });
    bubble('user', renderMarkdown(text));
    const answer = bubble('assistant', '<span class="typing">Agente está pensando…</span>');
    const typingEl = answer.querySelector('.typing');

    let full = '';
    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ model: 'chat-csa', messages: history, stream: true }),
      });
      if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const data = line.slice(5).trim();
          if (data === '[DONE]') continue;
          try {
            const j = JSON.parse(data);
            const delta = j.choices?.[0]?.delta?.content;
            if (delta) {
              full += delta;
              if (typingEl) typingEl.remove();
              answer.innerHTML = renderMarkdown(full);
              thread.scrollTop = thread.scrollHeight;
            }
          } catch { /* chunk malformado — ignora */ }
        }
      }
      history.push({ role: 'assistant', content: full });
    } catch (err) {
      if (typingEl) typingEl.remove();
      answer.innerHTML = 'Erro ao falar com o agente: ' + esc(String(err && err.message ? err.message : err));
      answer.className += ' bubble--error';
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  input.addEventListener('keydown', onKey);
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  });
  input.focus();
})();
"""


def _panel_page(user: dict) -> tuple:
    """Painel autenticado: chat SSE contra /v1/chat/completions (mesmo origin)."""
    return (
        Title("Painel do ingester"),
        Style(_BRAND_CSS),
        Div(
            Div(
                Div(
                    Div("Assistente CSA", cls="title"),
                    P(f"Painel do ingester — usuário {user['username']}", cls="sub"),
                ),
                Form(
                    Button("Sair", type="submit", cls="logout"),
                    method="post",
                    action="/admin/logout",
                ),
                cls="topbar",
            ),
            Div(
                Div(
                    P("Converse com o agente de ingestão para manter a base de conhecimento.", cls="empty"),
                    id="thread",
                    cls="thread",
                ),
                Form(
                    Textarea(
                        id="chat-input",
                        name="message",
                        placeholder="Digite sua pergunta…",
                        rows="1",
                        autocomplete="off",
                    ),
                    Button("Enviar", type="submit", id="chat-send"),
                    id="chat-form",
                    cls="composer",
                ),
                P("Enter envia · Shift+Enter quebra a linha", cls="hint"),
                Script(_CHAT_JS),
                cls="chat-wrap",
            ),
        ),
    )


def build_admin_panel() -> FastHTML:
    """Monta o app FastHTML do painel admin (montado em /admin no app principal)."""

    panel = FastHTML()

    @panel.get("/")
    async def index(request: Request):
        user = _get_user(request)
        if user is None:
            return _login_page()
        return _panel_page(user)

    @panel.post("/login")
    async def login(request: Request):
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        try:
            result = auth_store.login(username=username, password=password)
        except Exception:
            # Credenciais inválidas — reexibe o login com aviso
            return _login_page(error="Usuário ou senha inválidos.")
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie(
            _SESSION_COOKIE,
            result["access_token"],
            path="/admin",
            httponly=True,
            samesite="lax",
            secure=_COOKIE_SECURE,
        )
        return response

    @panel.post("/logout")
    async def logout(request: Request):
        response = RedirectResponse("/admin", status_code=303)
        response.delete_cookie(_SESSION_COOKIE, path="/admin")
        return response

    return panel