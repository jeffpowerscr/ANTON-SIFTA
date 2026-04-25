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
    assert result["error"] == "missing_target"


def test_autopilot_send_blocks_unallowlisted_target(monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    monkeypatch.setenv("SIFTA_WHATSAPP_ALLOWED_JIDS", "allowed@s.whatsapp.net")

    result = autopilot.send_message(to="other@s.whatsapp.net", message="hello")

    assert result["ok"] is False
    assert result["error"] == "target_not_allowlisted"


def test_autopilot_resolves_saved_alias(tmp_path, monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(
        '{"carlton": {"jid": "target@s.whatsapp.net", "jid_hash": "x"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(autopilot, "ALIAS_PATH", alias_path)

    result = autopilot.resolve_target("Carlton")

    assert result["ok"] is True
    assert result["jid"] == "target@s.whatsapp.net"
    assert result["alias"] == "carlton"


def test_autopilot_resolves_unique_contact_name_and_caches_alias(tmp_path, monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    contacts_path = tmp_path / "contacts.json"
    aliases_path = tmp_path / "aliases.json"
    contacts_path.write_text(
        """
        {
          "schema_version": 1,
          "contacts": {
            "target@s.whatsapp.net": {
              "jid": "target@s.whatsapp.net",
              "display_names": ["Carlton"]
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(autopilot, "CONTACTS_PATH", contacts_path)
    monkeypatch.setattr(autopilot, "ALIAS_PATH", aliases_path)

    result = autopilot.resolve_target("Carlton")

    assert result["ok"] is True
    assert result["jid"] == "target@s.whatsapp.net"
    assert result["alias"] == "carlton"
    assert "carlton" in aliases_path.read_text(encoding="utf-8")


def test_autopilot_reports_ambiguous_contact_name(tmp_path, monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    contacts_path = tmp_path / "contacts.json"
    contacts_path.write_text(
        """
        {
          "contacts": {
            "one@s.whatsapp.net": {"jid": "one@s.whatsapp.net", "display_names": ["Carlton"]},
            "two@s.whatsapp.net": {"jid": "two@s.whatsapp.net", "display_names": ["Carlton"]}
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(autopilot, "CONTACTS_PATH", contacts_path)
    monkeypatch.setattr(autopilot, "ALIAS_PATH", tmp_path / "aliases.json")

    result = autopilot.resolve_target("Carlton")

    assert result["ok"] is False
    assert result["error"] == "ambiguous_contact_name"
    assert len(result["matches"]) == 2


def test_autopilot_send_blocks_without_inject_key(monkeypatch):
    from System import whatsapp_bridge_autopilot as autopilot

    monkeypatch.setenv("SIFTA_WHATSAPP_ALLOWED_JIDS", "allowed@s.whatsapp.net")
    monkeypatch.delenv("SIFTA_BRIDGE_INJECT_KEY", raising=False)
    monkeypatch.setattr(autopilot, "RUNTIME_PATH", autopilot.STATE_DIR / "missing-test-runtime.json")

    result = autopilot.send_message(to="allowed@s.whatsapp.net", message="hello")

    assert result["ok"] is False
    assert result["error"] == "missing_inject_key"


def test_prompt_contract_names_autopilot_send_tool():
    from System.swarm_prompt_contract import tool_affordances_for_turn

    hint = tool_affordances_for_turn("send a whatsapp message")

    assert "System.whatsapp_bridge_autopilot status" in hint
    assert "whatsapp.bridge.resolve_contact" in hint
    assert "whatsapp.bridge.send" in hint
    assert "display name like Carlton" in hint
