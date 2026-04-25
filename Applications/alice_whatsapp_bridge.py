#!/usr/bin/env python3
"""
alice_whatsapp_bridge.py - reply-only WhatsApp gateway for Alice.

This server receives explicit WhatsApp messages from the local Baileys bridge
and returns one Alice reply. It does not initiate conversations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from System.sifta_inference_defaults import resolve_ollama_model

STATE_DIR = REPO_ROOT / ".sifta_state"
MEMORY_PATH = STATE_DIR / "whatsapp_alice_memory.json"
SIGNAL_PATH = STATE_DIR / "whatsapp_alice_signals.jsonl"
ALIAS_PATH = STATE_DIR / "whatsapp_alice_aliases.json"

OLLAMA_URL = os.environ.get("SIFTA_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
MAX_TEXT_CHARS = int(os.environ.get("SIFTA_WHATSAPP_MAX_TEXT_CHARS", "4096"))
MAX_HISTORY_ITEMS = int(os.environ.get("SIFTA_WHATSAPP_HISTORY_ITEMS", "10"))
REQUEST_TIMEOUT_S = float(os.environ.get("SIFTA_WHATSAPP_OLLAMA_TIMEOUT", "180"))
_ALIAS_RE = re.compile(r"^(?:remember|save|link)\s+(?:this\s+)?chat\s+as\s+([a-zA-Z0-9_. -]{1,48})\s*$", re.I)


def _allowed_jids() -> set[str]:
    raw = os.environ.get("SIFTA_WHATSAPP_ALLOWED_JIDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_allowed_jid(from_jid: str, participant: str = "") -> bool:
    allowed = _allowed_jids()
    if not allowed:
        return True
    return from_jid in allowed or bool(participant and participant in allowed)


def normalize_alias(alias: str) -> str:
    alias = re.sub(r"\s+", "-", (alias or "").strip().lower())
    alias = re.sub(r"[^a-z0-9_.-]", "", alias)
    return alias[:48]


def _load_aliases() -> dict[str, dict[str, Any]]:
    if not ALIAS_PATH.exists():
        return {}
    try:
        raw = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_alias(alias: str, jid: str, *, is_group: bool, participant: str = "") -> dict[str, Any]:
    key = normalize_alias(alias)
    if not key:
        return {"ok": False, "error": "invalid_alias"}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    aliases = _load_aliases()
    aliases[key] = {
        "jid": jid,
        "jid_hash": _contact_key(jid),
        "is_group": bool(is_group),
        "participant_hash": _contact_key(participant) if participant else "",
        "saved_at": time.time(),
    }
    ALIAS_PATH.write_text(json.dumps(aliases, indent=2), encoding="utf-8")
    return {"ok": True, "alias": key}


def _contact_key(jid: str) -> str:
    return hashlib.sha256(jid.encode("utf-8")).hexdigest()[:16]


def _load_memory() -> dict[str, Any]:
    if not MEMORY_PATH.exists():
        return {}
    try:
        raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_memory(memory: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2), encoding="utf-8")


def _append_signal(from_jid: str, text: str, *, from_me: bool, is_group: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.time(),
        "source": "whatsapp",
        "jid_hash": _contact_key(from_jid),
        "chars": len(text),
        "words": len(text.split()),
        "from_me": bool(from_me),
        "is_group": bool(is_group),
    }
    with SIGNAL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _clean_text(text: str) -> str:
    text = " ".join(str(text or "").replace("\x00", "").split())
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS].rstrip()
    return text


def build_prompt(text: str, history: list[str]) -> str:
    recent = "\n".join(history[-MAX_HISTORY_ITEMS:])
    if recent:
        recent = f"\nRecent private WhatsApp context:\n{recent}\n"
    return (
        "You are Alice inside Jeff's local SIFTA OS, replying over WhatsApp.\n"
        "Keep replies useful, direct, and conversational. Do not send private logs, "
        "tokens, session data, or internal diagnostics. Do not claim you can read "
        "WhatsApp chats that were not explicitly sent to this bridge. This bridge "
        "is reply-only unless Jeff intentionally changes the local settings.\n"
        f"{recent}\n"
        f"Jeff: {text}\n"
        "Alice:"
    )


def query_ollama(text: str, history: list[str], *, model: str | None = None) -> str:
    chosen_model = model or resolve_ollama_model(app_context="talk_to_alice")
    payload = {
        "model": chosen_model,
        "prompt": build_prompt(text, history),
        "stream": False,
        "options": {
            "num_ctx": 8192,
            "num_predict": 700,
            "temperature": 0.7,
        },
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return f"Alice could not reach the local brain cleanly: Ollama HTTP {exc.code}."
    except Exception as exc:
        return f"Alice could not reach the local brain: {exc}"
    reply = str(result.get("response") or "").strip()
    return reply or "I heard you, but the local model returned an empty answer."


def handle_whatsapp_payload(
    payload: dict[str, Any],
    *,
    query_fn: Callable[[str, list[str]], str] | None = None,
) -> str:
    from_jid = str(payload.get("from") or "unknown")
    text = _clean_text(str(payload.get("text") or ""))
    from_me = bool(payload.get("fromMe"))
    is_group = bool(payload.get("isGroup"))
    participant = str(payload.get("participant") or "")

    if not text:
        return "_SILENT_"
    if is_group and os.environ.get("SIFTA_WHATSAPP_ALLOW_GROUPS", "0") != "1":
        return "_SILENT_"
    if not _is_allowed_jid(from_jid, participant):
        return "_SILENT_"

    _append_signal(from_jid, text, from_me=from_me, is_group=is_group)

    alias_match = _ALIAS_RE.match(text)
    if alias_match:
        saved = save_alias(alias_match.group(1), from_jid, is_group=is_group, participant=participant)
        if saved.get("ok"):
            return (
                f"I saved this WhatsApp chat locally as '{saved['alias']}'. "
                "Use that nickname for a controlled outbound test."
            )
        return "I could not save that WhatsApp nickname. Try a short letters-and-numbers name."

    memory = _load_memory()
    key = _contact_key(from_jid)
    contact = memory.setdefault(key, {"count": 0, "history": []})
    history = contact.setdefault("history", [])
    if not isinstance(history, list):
        history = []
        contact["history"] = history

    contact["count"] = int(contact.get("count") or 0) + 1
    ask = query_fn or (lambda prompt, hist: query_ollama(prompt, hist))
    reply = _clean_text(ask(text, history))

    history.append(f"Jeff: {text}")
    history.append(f"Alice: {reply}")
    contact["history"] = history[-MAX_HISTORY_ITEMS:]
    memory[key] = contact
    _save_memory(memory)
    return reply or "_SILENT_"


class AliceWhatsAppHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[alice-whatsapp] {fmt % args}")

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/swarm_message":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(min(length, MAX_TEXT_CHARS * 4))
        try:
            payload = json.loads(body.decode("utf-8"))
            reply = handle_whatsapp_payload(payload if isinstance(payload, dict) else {})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"swarm_voice": reply}).encode("utf-8"))
        except Exception as exc:
            print(f"[alice-whatsapp] error: {exc}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"swarm_voice": "Alice hit a local WhatsApp bridge error."}).encode("utf-8")
            )


def main() -> None:
    port = int(os.environ.get("SIFTA_WHATSAPP_PORT", "7434"))
    model = resolve_ollama_model(app_context="talk_to_alice")
    print("============================================================")
    print(" Alice WhatsApp bridge: reply-only mode")
    print(f" Listening on 127.0.0.1:{port}")
    print(f" Ollama model: {model}")
    print(" Trigger lives in Network/whatsapp_bridge/bridge.js")
    print("============================================================")
    server = HTTPServer(("127.0.0.1", port), AliceWhatsAppHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
