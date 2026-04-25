from __future__ import annotations


def test_whatsapp_status_formats_reply_only_defaults(monkeypatch, tmp_path):
    from System import whatsapp_bridge_status as status

    session_dir = tmp_path / "whatsapp_session"
    session_dir.mkdir()
    (session_dir / "creds.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(status, "SESSION_DIR", session_dir)
    monkeypatch.setattr(status, "_port_open", lambda _host, port, timeout=0.25: port == 7434)

    data = status.status_dict()
    text = status.format_status(data)

    assert data["reply_server_online"] is True
    assert data["session_paired"] is True
    assert data["desktop_initiated_send_default"] == "disabled"
    assert "reply server: online" in text
    assert "Desktop-initiated sending: disabled" in text


def test_prompt_contract_knows_whatsapp_bridge_tool():
    from System.swarm_prompt_contract import tool_affordances_for_turn

    hint = tool_affordances_for_turn("can you send a whatsapp message like siri?")

    assert "System.whatsapp_bridge_autopilot status" in hint
    assert "reply-only" in hint
    assert "Siri" in hint
