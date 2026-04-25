def minimal_runtime_contract() -> str:
    """Tiny runtime contract with only technical constraints."""
    return (
        "RUNTIME CONSTRAINTS:\n"
        "- Use <bash>...</bash> to execute shell commands.\n"
        "- Ground answers in current context blocks.\n"
        "- If the Architect speaks via [iMessage], you MUST reply by executing:\n"
        "  <bash>python3 -m System.alice_body_autopilot --action iphone.send_text --hw-args '{\"payload\": \"Your message here\"}'</bash>"
    )

def grounding_block(focus: str) -> str:
    """Reserved compatibility hook for grounding blocks."""
    return ""

def tool_affordances_for_turn(user_text: str) -> str:
    """Return terse tool hints for grounded local capabilities."""
    text = (user_text or "").lower()
    if any(term in text for term in ("whatsapp", "whats app", "siri")):
        try:
            from System.sifta_tool_registry import tool_schema_prompt
            registered = tool_schema_prompt(
                only={
                    "whatsapp.bridge.status",
                    "whatsapp.bridge.aliases",
                    "whatsapp.bridge.resolve_contact",
                    "whatsapp.bridge.send",
                }
            )
        except Exception:
            registered = ""
        return (
            "WHATSAPP BRIDGE TOOL:\n"
            "- SIFTA has an experimental local WhatsApp bridge, not a native WhatsApp OS entitlement.\n"
            "- Prefer registered JSON tools over raw shell. To answer WhatsApp capability/status questions, call whatsapp.bridge.status.\n"
            "- Registered tool call shape example:\n"
            "  <tool_call>{\"name\":\"whatsapp.bridge.status\",\"arguments\":{}}</tool_call>\n"
            "- Shell fallback if structured tool calling is unavailable:\n"
            "  <bash>PYTHONPATH=. python3 -m System.whatsapp_bridge_autopilot status</bash>\n"
            "- Do not say Alice has no WhatsApp bridge if the status tool says the local reply server is online.\n"
            "- Current safe mode: reply-only. Alice answers WhatsApp messages that start with Alice, /alice, or @alice.\n"
            "- Group chats are muted by default. Autonomous outbound messages are disabled by default.\n"
            "- If asked whether Alice can send a new WhatsApp message from the desktop, say: not by default; "
            "desktop-initiated sending requires an explicit allowlisted local bridge configuration.\n"
            "- Normal WhatsApp users do not know JIDs. To create a safe target nickname, tell the user to send this from the target WhatsApp chat: Alice remember this chat as <nickname>.\n"
            "- If the user gives a display name like Carltonn, first call whatsapp.bridge.resolve_contact with {\"target\":\"Carltonn\"}. "
            "If exactly one match exists, use that resolved target/cache. If zero or multiple matches exist, ask the user to choose or save a nickname from the target chat.\n"
            "- List saved local target nicknames with:\n"
            "  <bash>PYTHONPATH=. python3 -m System.whatsapp_bridge_autopilot aliases</bash>\n"
            "- For a guarded outbound send attempt, use a display name that resolved uniquely, a saved allowlisted nickname, or an exact JID:\n"
            "  <tool_call>{\"name\":\"whatsapp.bridge.send\",\"arguments\":{\"to\":\"nickname\",\"message\":\"message here\"}}</tool_call>\n"
            "- Siri can send WhatsApp messages through iOS/WhatsApp-supported intents; Alice does not automatically inherit Siri's native app permissions."
            + ("\n\n" + registered if registered else "")
        )
    if any(term in text for term in ("surf", "swell", "wave report", "surfline", "jaco", "playa hermosa")):
        return (
            "SURF REPORT TOOL:\n"
            "- For live surf/swell questions, use public marine/weather data by executing:\n"
            "  <bash>PYTHONPATH=. python3 -m System.surf_report --spot jaco --day today</bash>\n"
            "- Change --spot and --day to match the user's request, e.g. --spot jaco --day thursday.\n"
            "- Do not scrape Surfline or ask for account passwords. Surfline Premium requires the user's logged-in browser or an official integration.\n"
            "- After the tool returns, summarize wave height, swell period/direction, wind/weather, tide caveat, nearby comparison, and a practical paddle-out read."
        )
    return ""
