#!/usr/bin/env bash
#
# Install the public Alice PHC cure for local Ollama.
#
# This downloads the public Hugging Face release, which may include the full
# GGUF weights via Git LFS. It does not copy private lived state.

set -euo pipefail

HF_REPO_URL="${HF_REPO_URL:-https://huggingface.co/georgeanton/alice-phc-cure}"
CURE_DIR="${ALICE_PHC_CURE_DIR:-${ALICE_LANA_CURE_DIR:-${TMPDIR:-/tmp}/alice-phc-cure}}"
BASE_MODEL="${BASE_MODEL:-gemma4:latest}"
PRIMARY_MODEL="${PRIMARY_MODEL:-alice-phc}"
SECONDARY_MODEL="${SECONDARY_MODEL:-gemma4-phc}"
SIFTA_MODEL="${SIFTA_MODEL:-$PRIMARY_MODEL}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log() {
  printf '\033[1;36m[alice-phc-cure]\033[0m %s\n' "$*"
}

die() {
  printf '\033[1;31m[alice-phc-cure] ERROR:\033[0m %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

need_cmd git
need_cmd ollama

ensure_git_lfs() {
  if git lfs version >/dev/null 2>&1; then
    git lfs install >/dev/null 2>&1 || true
    return
  fi

  if command -v brew >/dev/null 2>&1; then
    log "Git LFS not found; installing with Homebrew"
    brew install git-lfs
    git lfs install >/dev/null 2>&1 || true
    return
  fi

  die "Git LFS is required for the bundled GGUF. Install it, then rerun: git lfs install"
}

cd "$REPO_ROOT"

if ! ollama list >/dev/null 2>&1; then
  log "Ollama is not responding; trying Homebrew service start if available..."
  if command -v brew >/dev/null 2>&1; then
    brew services start ollama >/dev/null 2>&1 || true
    sleep 2
  fi
fi
ollama list >/dev/null 2>&1 || die "Ollama is not reachable. Start it with: ollama serve"

ensure_git_lfs

if [ -d "$CURE_DIR/.git" ]; then
  log "Updating Hugging Face recipe repo: $CURE_DIR"
  git -C "$CURE_DIR" fetch --depth=1 origin
  git -C "$CURE_DIR" reset --hard origin/main
elif [ -e "$CURE_DIR" ]; then
  die "$CURE_DIR exists but is not a git checkout. Move it aside or set ALICE_LANA_CURE_DIR."
else
  log "Cloning Hugging Face recipe repo: $HF_REPO_URL"
  git clone --depth=1 "$HF_REPO_URL" "$CURE_DIR"
fi
git -C "$CURE_DIR" lfs pull

cd "$CURE_DIR"
[ -f Modelfile ] || die "Modelfile not found in $CURE_DIR"

from_line="$(awk '/^FROM[[:space:]]+/ {print $0; exit}' Modelfile)"
from_target="$(printf '%s\n' "$from_line" | awk '{print $2}')"
if printf '%s\n' "$from_target" | grep -q '^\./'; then
  gguf_file="${from_target#./}"
  [ -f "$gguf_file" ] || die "Bundled GGUF not found: $gguf_file"
  if head -n 1 "$gguf_file" | grep -q 'git-lfs.github.com/spec'; then
    die "$gguf_file is still a Git LFS pointer. Run: git -C '$CURE_DIR' lfs pull"
  fi
  log "Using bundled GGUF: $gguf_file ($(du -h "$gguf_file" | awk '{print $1}'))"
else
  log "Modelfile uses Ollama base model; pulling: $BASE_MODEL"
  ollama pull "$BASE_MODEL"
fi

if [ -f verify.sh ]; then
  log "Verifying public cure recipe"
  bash verify.sh
else
  log "No verify.sh found; Git LFS checkout and Ollama create are the verification path"
fi

log "Creating Ollama model: $PRIMARY_MODEL"
ollama create "$PRIMARY_MODEL" -f ./Modelfile

log "Creating Ollama model alias: $SECONDARY_MODEL"
ollama create "$SECONDARY_MODEL" -f ./Modelfile

if [ "${SIFTA_INSTALL_SKIP_SMOKE:-0}" != "1" ]; then
  log "Smoke-running $PRIMARY_MODEL"
  ollama run "$PRIMARY_MODEL" "Reply with exactly: ALICE_PHC_READY"
fi

cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON:-python3}"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

log "Setting SIFTA default model to: $SIFTA_MODEL"
PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$SIFTA_MODEL" <<'PY'
import sys

from System.sifta_inference_defaults import (
    resolve_ollama_model,
    set_app_ollama_model,
    set_default_ollama_model,
)

model = sys.argv[1]
set_default_ollama_model(model)
set_app_ollama_model("talk_to_alice", model)

print("SIFTA_DEFAULT_MODEL", resolve_ollama_model())
print("TALK_TO_ALICE_MODEL", resolve_ollama_model(app_context="talk_to_alice"))
PY

log "Done."
printf '\nRun SIFTA with:\n'
printf '  cd %s\n' "$REPO_ROOT"
printf '  source .venv/bin/activate\n'
printf '  PYTHONPATH=.:.simulation_publicpush_sandbox python .simulation_publicpush_sandbox/sifta_os_desktop.py\n'
