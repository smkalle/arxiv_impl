#!/data/data/com.termux/files/usr/bin/bash
# Set LeafCX up on an Android phone under Termux.
#
# Termux has no Docker and no supported Ollama build, so the model runs through
# llama.cpp's llama-server and LeafCX talks to it over the OpenAI-compatible
# backend. Everything except the model weights is stdlib Python plus pytest.
set -euo pipefail

echo "==> packages"
pkg update -y
pkg install -y python git cmake clang

echo "==> python deps (pytest is the grader; nothing else is required)"
pip install --upgrade pip
pip install pytest

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT"

echo "==> harness self-check (no model needed)"
python3 -m pytest -q
python3 -m leafcx eval --backend gold --families shortlist_build --seeds 1-2 --no-transcript

cat <<'NEXT'

==> next: a model

llama.cpp, built on-device:

    git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
    cd ~/llama.cpp && cmake -B build && cmake --build build -j$(nproc)

Fetch a 4B GGUF (Q4_K_M is the practical default; ~2.5GB, needs ~4GB free RAM):

    pip install huggingface-hub
    hf download bartowski/Qwen_Qwen3.5-4B-GGUF \
        Qwen_Qwen3.5-4B-Q4_K_M.gguf --local-dir ~/models

Serve it. --jinja makes llama-server use the model's own chat template, which
is what drives tool calling:

    ~/llama.cpp/build/bin/llama-server \
        -m ~/models/Qwen_Qwen3.5-4B-Q4_K_M.gguf \
        --port 8080 -c 16384 --jinja

Then, in a second Termux session:

    export LEAFCX_BACKEND=openai
    export LEAFCX_BASE_URL=http://127.0.0.1:8080
    export LEAFCX_MODEL=qwen3.5-4b
    export LEAFCX_NUM_CTX=16384
    export LEAFCX_MAX_STEPS=25
    python3 -m leafcx doctor
    python3 -m leafcx run shortlist_build --seed 1

A phone will not hold the paper's 131k context. 16k and a 25-step budget is the
realistic setting; expect a few minutes per episode.

If the phone is the weak link, run llama-server on a laptop on the same network
and point LEAFCX_BASE_URL at it. The harness does not care where the model is.
NEXT
