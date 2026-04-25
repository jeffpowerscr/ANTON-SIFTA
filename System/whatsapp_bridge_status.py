#!/usr/bin/env python3
"""Report Alice's local WhatsApp bridge status."""
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = REPO_ROOT / "Network" / "whatsapp_bridge" / "whatsapp_session"


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
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


def status_dict() -> dict[str, object]:
    reply_server_online = _port_open("127.0.0.1", int(os.environ.get("SIFTA_WHATSAPP_PORT", "7434")))
    injection_server_online = _port_open("127.0.0.1", 3001)
    session_files = sorted(SESSION_DIR.glob("*.json")) if SESSION_DIR.exists() else []
    session_paired = (SESSION_DIR / "creds.json").exists()
    return {
        "bridge": "alice_whatsapp",
        "reply_server_online": reply_server_online,
        "reply_server_port": int(os.environ.get("SIFTA_WHATSAPP_PORT", "7434")),
        "session_dir_exists": SESSION_DIR.exists(),
        "session_paired": session_paired,
        "session_file_count": len(session_files),
        "trigger_words": ["Alice", "/alice", "@alice"],
        "default_mode": "reply_only",
        "group_chats_default": "muted",
        "desktop_initiated_send_default": "disabled",
        "injection_server_online": injection_server_online,
        "notes": [
            "WhatsApp replies work by messaging Alice from WhatsApp with a trigger word.",
            "The desktop Alice app does not have native WhatsApp OS entitlements.",
            "Desktop-initiated WhatsApp sending is intentionally disabled unless an allowlisted local bridge is configured.",
        ],
    }


def format_status(data: dict[str, object]) -> str:
    reply = "online" if data["reply_server_online"] else "offline"
    paired = "paired session present" if data["session_paired"] else "not paired yet"
    inject = "enabled/listening" if data["injection_server_online"] else "disabled"
    return "\n".join(
        [
            "Alice WhatsApp bridge status:",
            f"- Local reply server: {reply} on 127.0.0.1:{data['reply_server_port']}",
            f"- WhatsApp session: {paired} ({data['session_file_count']} local session files)",
            "- Trigger: send a WhatsApp message starting with Alice, /alice, or @alice",
            f"- Default group behavior: {data['group_chats_default']}",
            f"- Desktop-initiated sending: {data['desktop_initiated_send_default']}",
            f"- Outbound injection server: {inject}",
        ]
    )


def main() -> None:
    data = status_dict()
    if os.environ.get("SIFTA_STATUS_JSON") == "1":
        print(json.dumps(data, indent=2))
    else:
        print(format_status(data))


if __name__ == "__main__":
    main()
