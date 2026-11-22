"""Cliente no formato do Ollama apontando para o shim do Chat CSA.

O provedor do modelo é o OpenRouter; este exemplo exercita apenas a superfície
HTTP compatível com o protocolo do Ollama (`POST /api/chat`).
"""
import httpx

# O servidor expõe /api/chat no formato do Ollama, mas quem responde é o OpenRouter
r = httpx.post("http://localhost:8001/api/chat", json={
    "model": "chat-csa",
    "messages": [{"role": "user", "content": "quando sai o resultado?"}],
    "stream": False,
})
print(r.json())

# streaming via ndjson
print("\n--- streaming ---\n")
with httpx.stream("POST", "http://localhost:8001/api/chat", json={
    "model": "chat-csa",
    "messages": [{"role": "user", "content": "oi"}],
    "stream": True,
}) as s:
    for line in s.iter_lines():
        if line:
            print(line)
