#!/bin/sh
set -eu
cd /models
printf '%s  %s\n' a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299 apertus-v1.5-8b-text-q4_k_m.gguf | sha256sum -c -
test -s server.key
export LD_LIBRARY_PATH=/app
cd /app
exec /app/llama-server \
  --model /models/apertus-v1.5-8b-text-q4_k_m.gguf \
  --alias Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF \
  --host 0.0.0.0 --port 8080 --ctx-size 16384 --parallel 1 \
  --threads 6 --threads-batch 8 --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --api-key-file /models/server.key --no-webui --log-disable
