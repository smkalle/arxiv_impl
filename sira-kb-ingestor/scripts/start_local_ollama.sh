#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11435}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$ROOT_DIR/.ollama-models}"

mkdir -p "$OLLAMA_MODELS"

echo "Starting Ollama"
echo "  OLLAMA_HOST=$OLLAMA_HOST"
echo "  OLLAMA_MODELS=$OLLAMA_MODELS"
echo
echo "In another shell, use:"
echo "  export OLLAMA_HOST=http://$OLLAMA_HOST"
echo "  ollama pull qwen2.5-coder:3b"
echo

exec ollama serve
