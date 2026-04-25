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
import socket
import urllib.error
import urllib.request
from typing import Any

from System.whatsapp_bridge_status import format_status, status_dict

INJECT_URL = os.environ.get("SIFTA_WHATSAPP_INJECT_URL", "http://127.0.0.1:3001/system_inject")
INJECT_PORT = int(os.environ.get("SIFTA_WHATSAPP_INJECT_PORT", "3001"))


def _port_open(host: str = "127.0.0.1", port: int = INJECT_PORT, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _allowed_jids() -> set[str]:
    raw = os.environ.get("SIFTA_WHATSAPP_ALLOWED_JIDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _result(ok: bool, **fields: Any) -> dict[str, Any]:
    out = {"ok": ok}
    out.update(fields)
    return out


def send_message(*, to: str, message: str) -> dict[str, Any]:
    to = (to or "").strip()
    message = (message or "").strip()
    if not message:
        return _result(False, error="missing_message")
    if not to:
        return _result(
            False,
            error="missing_target_jid",
            help="Desktop WhatsApp sending needs an exact allowlisted WhatsApp JID, not only a contact name.",
        )

    allowed = _allowed_jids()
    if to not in allowed:
        return _result(
            False,
            error="target_not_allowlisted",
            target=to,
            help="Set SIFTA_WHATSAPP_ALLOWED_JIDS to the exact WhatsApp JID before enabling outbound sends.",
        )

    key = os.environ.get("SIFTA_BRIDGE_INJECT_KEY", "").strip()
    if not key:
        return _result(
            False,
            error="missing_inject_key",
            help="SIFTA_BRIDGE_INJECT_KEY is not available to this process, so Alice cannot send WhatsApp messages from the desktop.",
        )

    if not _port_open():
        return _result(
            False,
            error="inject_server_offline",
            help="Restart the WhatsApp bridge with SIFTA_WHATSAPP_ENABLE_INJECT=1 and the same allowlisted JID.",
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
            return _result(True, target=to, bridge_response=remote)
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
    parser.add_argument("command", nargs="?", choices=("status", "send"), help="Action to perform")
    parser.add_argument("--action", choices=("status", "send"), help="Compatibility alias for command")
    parser.add_argument("--to", "--jid", dest="to", default="", help="Exact allowlisted WhatsApp JID")
    parser.add_argument("--message", "--text", "--payload", dest="message", default="", help="Message to send")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    command = args.action or args.command or "status"
    if command == "status":
        data = status_dict()
        data["outbound_send_requirements"] = [
            "SIFTA_WHATSAPP_ENABLE_INJECT=1 on the Node bridge",
            "SIFTA_BRIDGE_INJECT_KEY shared with this process",
            "SIFTA_WHATSAPP_ALLOWED_JIDS containing the exact target JID",
        ]
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(format_status(data))
            print("Outbound desktop send: guarded/off by default.")
            print("To send, configure injection + an exact allowlisted WhatsApp JID.")
        return 0

    result = send_message(to=args.to, message=args.message)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 2
    return _print_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
