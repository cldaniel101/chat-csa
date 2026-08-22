# Exemplos de curl

## Compatibilidade OpenAI

curl http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"hello"}]}'

# streaming
curl -N http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"hello"}],"stream":true}'

## Shim do Ollama

curl http://localhost:8001/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"oi"}]}'

curl -N http://localhost:8001/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-csa","messages":[{"role":"user","content":"oi"}],"stream":true}'