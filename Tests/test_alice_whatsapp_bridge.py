from __future__ import annotations

import json


def test_whatsapp_bridge_handles_explicit_payload_without_raw_jid(tmp_path, monkeypatch):
    from Applications import alice_whatsapp_bridge as bridge

    monkeypatch.setattr(bridge, "STATE_DIR", tmp_path)
    monkeypatch.setattr(bridge, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(bridge, "SIGNAL_PATH", tmp_path / "signals.jsonl")
    monkeypatch.delenv("SIFTA_WHATSAPP_ALLOW_GROUPS", raising=False)

    reply = bridge.handle_whatsapp_payload(
        {"from": "15551234567@s.whatsapp.net", "text": "can you hear me", "fromMe": True},
        query_fn=lambda text, history: f"heard: {text}",
    )

    assert reply == "heard: can you hear me"
    assert bridge.MEMORY_PATH.exists()
    assert bridge.SIGNAL_PATH.exists()
    assert "15551234567" not in bridge.MEMORY_PATH.read_text(encoding="utf-8")
    signal = json.loads(bridge.SIGNAL_PATH.read_text(encoding="utf-8").splitlines()[0])
    assert signal["source"] == "whatsapp"
    assert signal["from_me"] is True


def test_whatsapp_bridge_mutes_groups_by_default(tmp_path, monkeypatch):
    from Applications import alice_whatsapp_bridge as bridge

    monkeypatch.setattr(bridge, "STATE_DIR", tmp_path)
    monkeypatch.setattr(bridge, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(bridge, "SIGNAL_PATH", tmp_path / "signals.jsonl")
    monkeypatch.delenv("SIFTA_WHATSAPP_ALLOW_GROUPS", raising=False)

    reply = bridge.handle_whatsapp_payload(
        {"from": "12345@g.us", "text": "alice hello", "isGroup": True},
        query_fn=lambda _text, _history: "should not run",
    )

    assert reply == "_SILENT_"
    assert not bridge.MEMORY_PATH.exists()
    assert not bridge.SIGNAL_PATH.exists()


def test_whatsapp_bridge_honors_allowed_jids(tmp_path, monkeypatch):
    from Applications import alice_whatsapp_bridge as bridge

    monkeypatch.setattr(bridge, "STATE_DIR", tmp_path)
    monkeypatch.setattr(bridge, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(bridge, "SIGNAL_PATH", tmp_path / "signals.jsonl")
    monkeypatch.setenv("SIFTA_WHATSAPP_ALLOWED_JIDS", "allowed@s.whatsapp.net")

    blocked = bridge.handle_whatsapp_payload(
        {"from": "other@s.whatsapp.net", "text": "alice hello"},
        query_fn=lambda _text, _history: "should not run",
    )
    allowed = bridge.handle_whatsapp_payload(
        {"from": "allowed@s.whatsapp.net", "text": "alice hello"},
        query_fn=lambda text, _history: f"ok: {text}",
    )

    assert blocked == "_SILENT_"
    assert allowed == "ok: alice hello"


def test_whatsapp_bridge_saves_alias_from_chat(tmp_path, monkeypatch):
    from Applications import alice_whatsapp_bridge as bridge

    monkeypatch.setattr(bridge, "STATE_DIR", tmp_path)
    monkeypatch.setattr(bridge, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(bridge, "SIGNAL_PATH", tmp_path / "signals.jsonl")
    monkeypatch.setattr(bridge, "ALIAS_PATH", tmp_path / "aliases.json")

    reply = bridge.handle_whatsapp_payload(
        {"from": "target@s.whatsapp.net", "text": "remember this chat as Carlton N"},
        query_fn=lambda _text, _history: "should not run",
    )

    assert "carlton-n" in reply
    assert bridge.ALIAS_PATH.exists()
