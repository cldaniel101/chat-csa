"""Exemplo com o SDK da OpenAI contra o agente local (ingester ou consumer)."""
from openai import OpenAI

# Aponte para o seu agente local (garanta que está rodando: make run-ingester)
client = OpenAI(base_url="http://localhost:8001/v1", api_key="sk-fake")

resp = client.chat.completions.create(
    model="chat-csa",
    messages=[{"role": "user", "content": "quais documentos para matrícula?"}],
    stream=False,
)
print(resp.choices[0].message.content)

# streaming
print("\n--- streaming ---\n")
stream = client.chat.completions.create(
    model="chat-csa",
    messages=[{"role": "user", "content": "explique a lista de espera"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
