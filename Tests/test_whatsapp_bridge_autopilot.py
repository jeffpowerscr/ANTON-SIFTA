from __future__ import annotations


def test_autopilot_status_command_mentions_guarded_send(capsys):
    from System import whatsapp_bridge_autopilot as autopilot

    rc = autopilot.main(["status"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Alice WhatsApp bridge status:" in out
    assert "Outbound desktop send: guarded/off by default." in out


def test_autopilot_send_blocks_without_target():
    from System import whatsapp_bridge_autopilot as autopilot

    result = autopilot.send_message(to="", message="hello")

    assert result["ok"] is False
    assert result["error"] == "missing_target_jid"


def test_autopilot_send_blocks_unallowlisted_target(monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    monkeypatch.setenv("SIFTA_WHATSAPP_ALLOWED_JIDS", "allowed@s.whatsapp.net")

    result = autopilot.send_message(to="other@s.whatsapp.net", message="hello")

    assert result["ok"] is False
    assert result["error"] == "target_not_allowlisted"


def test_autopilot_send_blocks_without_inject_key(monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    monkeypatch.setenv("SIFTA_WHATSAPP_ALLOWED_JIDS", "allowed@s.whatsapp.net")
    monkeypatch.delenv("SIFTA_BRIDGE_INJECT_KEY", raising=False)

    result = autopilot.send_message(to="allowed@s.whatsapp.net", message="hello")

    assert result["ok"] is False
    assert result["error"] == "missing_inject_key"


def test_prompt_contract_names_autopilot_send_tool():
    from System.swarm_prompt_contract import tool_affordances_for_turn

    hint = tool_affordances_for_turn("send a whatsapp message")

    assert "System.whatsapp_bridge_autopilot status" in hint
    assert "System.whatsapp_bridge_autopilot send" in hint
    assert "exact allowlisted WhatsApp JID" in hint
