"""Cliente compatível com Ollama (usa o formato da API do Ollama, mas aponta para o nosso shim)."""
import httpx

# Nosso servidor também fala o /api/chat do Ollama
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
