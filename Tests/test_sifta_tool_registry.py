from __future__ import annotations


def test_whatsapp_tools_registered_with_json_schema():
    from System.sifta_tool_registry import TOOL_REGISTRY, tool_schema_prompt

    send = TOOL_REGISTRY["whatsapp.bridge.send"]

    assert "whatsapp.bridge.status" in TOOL_REGISTRY
    assert "whatsapp.bridge.aliases" in TOOL_REGISTRY
    assert "whatsapp.bridge.resolve_contact" in TOOL_REGISTRY
    assert send.parameters["required"] == ["to", "message"]
    assert send.parameters["properties"]["to"]["type"] == "string"
    assert send.parameters["properties"]["message"]["type"] == "string"
    prompt = tool_schema_prompt(only={"whatsapp.bridge.send"})
    assert "<tool_call>" in prompt
    assert "whatsapp.bridge.send" in prompt


def test_registered_tool_execution_validates_arguments():
    from System.sifta_tool_registry import execute_tool_call

    unknown = execute_tool_call("nope", {})
    missing = execute_tool_call("whatsapp.bridge.send", {"to": "carlton"})

    assert unknown["ok"] is False
    assert unknown["error"] == "unknown_tool"
    assert missing["ok"] is False
    assert "missing required argument: message" in missing["error"]


def test_registered_contact_resolution_tool_validates_target():
    from System.sifta_tool_registry import TOOL_REGISTRY, execute_tool_call

    resolve = TOOL_REGISTRY["whatsapp.bridge.resolve_contact"]
    missing = execute_tool_call("whatsapp.bridge.resolve_contact", {})

    assert resolve.parameters["required"] == ["target"]
    assert missing["ok"] is False
    assert "missing required argument: target" in missing["error"]


def test_alice_widget_extracts_registered_tool_calls():
    from Applications.sifta_talk_to_alice_widget import (
        _extract_registered_tool_calls,
        _has_incomplete_registered_tool_call,
        _registered_tool_call_from_shell_command,
    )

    calls = _extract_registered_tool_calls(
        '<tool_call>{"name":"whatsapp.bridge.send","arguments":{"to":"carlton","message":"hello"}}</tool_call>'
    )

    assert calls == [
        {
            "name": "whatsapp.bridge.send",
            "arguments": {"to": "carlton", "message": "hello"},
        }
    ]
    assert _has_incomplete_registered_tool_call('<tool_call>{"name":"whatsapp.bridge.send","arguments":{"to":') is True
    assert _has_incomplete_registered_tool_call('<tool_call>{"name":"whatsapp.bridge.status","arguments":{}}</tool_call>') is False
    assert _registered_tool_call_from_shell_command("whatsapp.bridge.send --to carlton --message success") == {
        "name": "whatsapp.bridge.send",
        "arguments": {"to": "carlton", "message": "success"},
    }
    assert _registered_tool_call_from_shell_command("whatsapp.bridge.resolve_contact Carlton") == {
        "name": "whatsapp.bridge.resolve_contact",
        "arguments": {"target": "Carlton"},
    }


def test_whatsapp_prompt_includes_registered_schema():
    from System.swarm_prompt_contract import tool_affordances_for_turn

    hint = tool_affordances_for_turn("can alice use whatsapp?")

    assert "REGISTERED LOCAL TOOLS" in hint
    assert "whatsapp.bridge.status" in hint
    assert "whatsapp.bridge.resolve_contact" in hint
    assert "whatsapp.bridge.send" in hint
    assert '"required": [' in hint
