#!/usr/bin/env python3
"""Local tool registry for Alice's structured tool calls.

The Talk-to-Alice widget can already run explicit <bash> commands. This
registry is the safer, named-tool layer: it advertises tool schemas to Alice and
executes a small allowlist of Python functions without shell interpolation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], dict[str, Any]]


def _whatsapp_status(_args: Mapping[str, Any]) -> dict[str, Any]:
    from System.whatsapp_bridge_autopilot import status_dict

    return {"ok": True, "status": status_dict()}


def _whatsapp_aliases(_args: Mapping[str, Any]) -> dict[str, Any]:
    from System.whatsapp_bridge_autopilot import list_aliases

    return {"ok": True, "aliases": list_aliases()}


def _whatsapp_resolve_contact(args: Mapping[str, Any]) -> dict[str, Any]:
    from System.whatsapp_bridge_autopilot import resolve_target

    return resolve_target(str(args.get("target") or ""))


def _whatsapp_send(args: Mapping[str, Any]) -> dict[str, Any]:
    from System.whatsapp_bridge_autopilot import send_message

    return send_message(to=str(args.get("to") or ""), message=str(args.get("message") or ""))


TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "whatsapp.bridge.status": ToolSpec(
        name="whatsapp.bridge.status",
        description="Report the local Alice WhatsApp bridge status and saved target aliases.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_whatsapp_status,
    ),
    "whatsapp.bridge.aliases": ToolSpec(
        name="whatsapp.bridge.aliases",
        description="List saved local WhatsApp target nicknames.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_whatsapp_aliases,
    ),
    "whatsapp.bridge.resolve_contact": ToolSpec(
        name="whatsapp.bridge.resolve_contact",
        description=(
            "Resolve a WhatsApp display name, saved nickname, or exact JID to the local bridge target. "
            "If exactly one display-name match exists, it is cached as a local nickname."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Display name, saved nickname, or exact WhatsApp JID to resolve.",
                },
            },
            "required": ["target"],
            "additionalProperties": False,
        },
        handler=_whatsapp_resolve_contact,
    ),
    "whatsapp.bridge.send": ToolSpec(
        name="whatsapp.bridge.send",
        description=(
            "Guarded WhatsApp send through the local bridge. Requires a saved/allowlisted "
            "nickname or exact JID and outbound bridge injection enabled."
        ),
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Saved local nickname, e.g. carltonn, or exact allowlisted WhatsApp JID.",
                },
                "message": {
                    "type": "string",
                    "description": "The exact WhatsApp message text Alice intends to send.",
                },
            },
            "required": ["to", "message"],
            "additionalProperties": False,
        },
        handler=_whatsapp_send,
    ),
}


def _validate_args(spec: ToolSpec, args: Mapping[str, Any]) -> str | None:
    schema = spec.parameters
    required = schema.get("required") or []
    for name in required:
        if name not in args or args.get(name) in (None, ""):
            return f"missing required argument: {name}"
    allowed = set((schema.get("properties") or {}).keys())
    if schema.get("additionalProperties") is False:
        extra = sorted(set(args.keys()) - allowed)
        if extra:
            return f"unexpected argument(s): {', '.join(extra)}"
    return None


def execute_tool_call(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    spec = TOOL_REGISTRY.get(str(name or "").strip())
    if spec is None:
        return {"ok": False, "error": "unknown_tool", "tool": name}
    args = arguments or {}
    if not isinstance(args, Mapping):
        return {"ok": False, "error": "arguments_must_be_object", "tool": spec.name}
    err = _validate_args(spec, args)
    if err:
        return {"ok": False, "error": err, "tool": spec.name}
    try:
        result = spec.handler(args)
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        result.setdefault("tool", spec.name)
        return result
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "tool": spec.name}


def tool_schema_prompt(*, only: set[str] | None = None) -> str:
    specs = [spec for name, spec in TOOL_REGISTRY.items() if only is None or name in only]
    rows = [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        }
        for spec in specs
    ]
    return (
        "REGISTERED LOCAL TOOLS:\n"
        "Use this exact form when a registered tool is needed:\n"
        "<tool_call>{\"name\":\"tool.name\",\"arguments\":{...}}</tool_call>\n"
        "Do not invent unregistered modules or tool names.\n"
        + json.dumps(rows, indent=2)
    )


def main() -> None:
    print(tool_schema_prompt())


if __name__ == "__main__":
    main()
