#!/usr/bin/env python3
"""Guarded outbound controller for Alice's local WhatsApp bridge.

This module exists so Alice never reports a missing WhatsApp send organ. It is
deliberately conservative: outbound sends only work when the bridge was started
with injection enabled, an injection key is present in this process, and the
target WhatsApp JID is allowlisted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from System.whatsapp_bridge_status import format_status, status_dict

INJECT_URL = os.environ.get("SIFTA_WHATSAPP_INJECT_URL", "http://127.0.0.1:3001/system_inject")
INJECT_PORT = int(os.environ.get("SIFTA_WHATSAPP_INJECT_PORT", "3001"))
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / ".sifta_state"
ALIAS_PATH = STATE_DIR / "whatsapp_alice_aliases.json"
CONTACTS_PATH = STATE_DIR / "whatsapp_contacts.json"
RUNTIME_PATH = STATE_DIR / "whatsapp_bridge_runtime.json"


def _port_open(host: str = "127.0.0.1", port: int = INJECT_PORT, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        pass
    try:
        proc = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        return proc.returncode == 0 and f":{port} " in proc.stdout
    except Exception:
        return False


def _allowed_jids() -> set[str]:
    raw = os.environ.get("SIFTA_WHATSAPP_ALLOWED_JIDS", "") or str(_runtime().get("allowed_jids", ""))
    return {item.strip() for item in raw.split(",") if item.strip()}


def _allowed_aliases() -> set[str]:
    raw = os.environ.get("SIFTA_WHATSAPP_ALLOWED_ALIASES", "") or str(_runtime().get("allowed_aliases", ""))
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _runtime() -> dict[str, Any]:
    if not RUNTIME_PATH.exists():
        return {}
    try:
        raw = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


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


def _write_aliases(aliases: dict[str, dict[str, Any]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ALIAS_PATH.write_text(json.dumps(aliases, indent=2), encoding="utf-8")


def _normalize_lookup(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return re.sub(r"[^a-z0-9+@._ -]", "", value)


def _normalize_alias(value: str) -> str:
    value = re.sub(r"\s+", "-", (value or "").strip().lower())
    value = re.sub(r"[^a-z0-9_.-]", "", value)
    return value[:48]


def _load_contacts() -> dict[str, dict[str, Any]]:
    if not CONTACTS_PATH.exists():
        return {}
    try:
        raw = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("contacts"), dict):
        rows = raw["contacts"]
    elif isinstance(raw, dict):
        rows = raw
    else:
        return {}
    contacts: dict[str, dict[str, Any]] = {}
    for jid, row in rows.items():
        if not isinstance(row, dict):
            continue
        real_jid = str(row.get("jid") or jid)
        if "@" not in real_jid:
            continue
        contacts[real_jid] = row | {"jid": real_jid}
    return contacts


def _contact_names(row: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "notify", "pushName", "verifiedName", "subject", "displayName"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    display_names = row.get("display_names")
    if isinstance(display_names, list):
        names.extend(str(item).strip() for item in display_names if str(item).strip())
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(names))


def _contact_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    jid = str(row.get("jid") or "")
    names = _contact_names(row)
    return {
        "name": names[0] if names else "(unnamed)",
        "jid": jid,
        "jid_hash": _jid_hash(jid),
        "is_group": bool(row.get("is_group")),
    }


def _jid_hash(jid: str) -> str:
    import hashlib

    return hashlib.sha256(jid.encode("utf-8")).hexdigest()[:12]


def _cache_alias(alias: str, jid: str, *, source: str) -> str:
    key = _normalize_alias(alias)
    if not key:
        return ""
    aliases = _load_aliases()
    aliases[key] = {
        "jid": jid,
        "jid_hash": _jid_hash(jid),
        "source": source,
    }
    _write_aliases(aliases)
    return key


def search_contacts(query: str) -> dict[str, Any]:
    q_norm = _normalize_lookup(query)
    if not q_norm:
        return {"ok": False, "error": "missing_query", "matches": []}
    contacts = _load_contacts()
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for row in contacts.values():
        names = _contact_names(row)
        norm_names = [_normalize_lookup(name) for name in names]
        if q_norm in norm_names:
            exact.append(row)
        elif any(q_norm in name or name in q_norm for name in norm_names if name):
            partial.append(row)
    rows = exact or partial
    summaries = [_contact_summary(row) for row in rows]
    return {
        "ok": True,
        "query": query,
        "match_type": "exact" if exact else "partial",
        "matches": summaries,
    }


def resolve_target(target: str) -> dict[str, Any]:
    target = (target or "").strip()
    aliases = _load_aliases()
    key = _normalize_alias(target)
    if key in aliases and aliases[key].get("jid"):
        return {"ok": True, "jid": str(aliases[key]["jid"]), "alias": key}
    if "@" in target:
        return {"ok": True, "jid": target, "alias": ""}
    found = search_contacts(target)
    matches = found.get("matches") if found.get("ok") else []
    if isinstance(matches, list) and len(matches) == 1:
        jid = str(matches[0].get("jid") or "")
        alias = _cache_alias(target, jid, source="contact_resolution")
        return {
            "ok": True,
            "jid": jid,
            "alias": alias,
            "resolved_from": "contact_search",
            "contact": matches[0],
        }
    if isinstance(matches, list) and len(matches) > 1:
        return {
            "ok": False,
            "error": "ambiguous_contact_name",
            "matches": matches[:8],
            "help": "Multiple WhatsApp contacts/chats matched. Ask the user which one to use, or save a unique nickname from the target chat.",
        }
    return {
        "ok": False,
        "error": "unknown_contact_alias_or_jid",
        "help": "No unique WhatsApp contact match. From the target chat, send: Alice remember this chat as <nickname>.",
    }


def list_aliases() -> list[str]:
    return sorted(_load_aliases().keys())


def _result(ok: bool, **fields: Any) -> dict[str, Any]:
    out = {"ok": ok}
    out.update(fields)
    return out


def send_message(*, to: str, message: str) -> dict[str, Any]:
    original_to = (to or "").strip()
    message = (message or "").strip()
    if not message:
        return _result(False, error="missing_message")
    if not original_to:
        return _result(
            False,
            error="missing_target",
            help="Use a saved local nickname or an exact WhatsApp JID.",
        )
    resolved = resolve_target(original_to)
    if not resolved.get("ok"):
        return _result(False, **resolved)
    to = str(resolved["jid"])
    alias = str(resolved.get("alias") or "")

    allowed = _allowed_jids()
    allowed_aliases = _allowed_aliases()
    if to not in allowed and (not alias or alias not in allowed_aliases):
        return _result(
            False,
            error="target_not_allowlisted",
            target=original_to,
            alias=alias,
            help="Set SIFTA_WHATSAPP_ALLOWED_ALIASES to the saved nickname, or allowlist the exact JID.",
        )

    key = os.environ.get("SIFTA_BRIDGE_INJECT_KEY", "").strip() or str(_runtime().get("inject_key", "")).strip()
    if not key:
        return _result(
            False,
            error="missing_inject_key",
            help="SIFTA_BRIDGE_INJECT_KEY is not available. Restart the bridge with injection enabled so it writes local runtime config.",
        )

    if not _port_open():
        return _result(
            False,
            error="inject_server_offline",
            help="Restart the WhatsApp bridge with SIFTA_WHATSAPP_ENABLE_INJECT=1 and the saved alias allowlisted.",
        )

    payload = json.dumps({"to": to, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        INJECT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Sifta-Inject-Key": key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                remote = json.loads(body)
            except json.JSONDecodeError:
                remote = {"raw": body}
            return _result(True, target=original_to, jid=to, alias=alias, bridge_response=remote)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return _result(False, error=f"http_{exc.code}", detail=body)
    except Exception as exc:
        return _result(False, error=type(exc).__name__, detail=str(exc))


def _print_result(data: dict[str, Any]) -> int:
    if data.get("ok"):
        print(f"WHATSAPP_SEND_OK target={data.get('target', '')}")
        return 0
    print("WHATSAPP_SEND_BLOCKED")
    print(f"error: {data.get('error', 'unknown')}")
    if data.get("help"):
        print(f"help: {data['help']}")
    if data.get("target"):
        print(f"target: {data['target']}")
    if data.get("detail"):
        print(f"detail: {data['detail']}")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded WhatsApp bridge autopilot")
    parser.add_argument("command", nargs="?", choices=("status", "aliases", "resolve", "search", "send"), help="Action to perform")
    parser.add_argument("--action", choices=("status", "aliases", "resolve", "search", "send"), help="Compatibility alias for command")
    parser.add_argument("--to", "--jid", dest="to", default="", help="Exact allowlisted WhatsApp JID")
    parser.add_argument("--target", "--name", dest="target", default="", help="Display name, saved nickname, or JID to resolve")
    parser.add_argument("--message", "--text", "--payload", dest="message", default="", help="Message to send")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    command = args.action or args.command or "status"
    if command == "status":
        data = status_dict()
        data["saved_aliases"] = list_aliases()
        data["outbound_send_requirements"] = [
            "SIFTA_WHATSAPP_ENABLE_INJECT=1 on the Node bridge",
            "SIFTA_BRIDGE_INJECT_KEY shared with this process",
            "SIFTA_WHATSAPP_ALLOWED_ALIASES containing the saved local nickname, or SIFTA_WHATSAPP_ALLOWED_JIDS containing the exact target JID",
        ]
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(format_status(data))
            print("Outbound desktop send: guarded/off by default.")
            aliases = ", ".join(data["saved_aliases"]) or "(none)"
            print(f"Saved local WhatsApp aliases: {aliases}")
            print("To send, configure injection + a saved allowlisted nickname.")
        return 0

    if command == "aliases":
        aliases = list_aliases()
        if args.json:
            print(json.dumps({"ok": True, "aliases": aliases}, indent=2))
        else:
            print("\n".join(aliases) if aliases else "No saved WhatsApp aliases yet.")
        return 0

    if command in {"resolve", "search"}:
        target = args.target or args.to
        data = search_contacts(target) if command == "search" else resolve_target(target)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            if data.get("ok"):
                if command == "resolve":
                    print(f"WHATSAPP_RESOLVE_OK target={target} jid={data.get('jid')} alias={data.get('alias', '')}")
                else:
                    matches = data.get("matches") or []
                    print(json.dumps(matches, indent=2))
            else:
                print("WHATSAPP_RESOLVE_BLOCKED")
                print(f"error: {data.get('error', 'unknown')}")
                if data.get("help"):
                    print(f"help: {data['help']}")
                if data.get("matches"):
                    print(json.dumps(data["matches"], indent=2))
        return 0 if data.get("ok") else 2

    result = send_message(to=args.to, message=args.message)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 2
    return _print_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
