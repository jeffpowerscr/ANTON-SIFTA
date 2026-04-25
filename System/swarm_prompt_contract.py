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
        return (
            "WHATSAPP BRIDGE TOOL:\n"
            "- SIFTA has an experimental local WhatsApp bridge, not a native WhatsApp OS entitlement.\n"
            "- To answer WhatsApp capability/status questions, execute:\n"
            "  <bash>PYTHONPATH=. python3 -m System.whatsapp_bridge_autopilot status</bash>\n"
            "- Do not say Alice has no WhatsApp bridge if the status tool says the local reply server is online.\n"
            "- Current safe mode: reply-only. Alice answers WhatsApp messages that start with Alice, /alice, or @alice.\n"
            "- Group chats are muted by default. Autonomous outbound messages are disabled by default.\n"
            "- If asked whether Alice can send a new WhatsApp message from the desktop, say: not by default; "
            "desktop-initiated sending requires an explicit allowlisted local bridge configuration.\n"
            "- Do not invent contact JIDs from names like Carlton. For a guarded outbound send attempt, the user must provide an exact allowlisted WhatsApp JID; then execute:\n"
            "  <bash>PYTHONPATH=. python3 -m System.whatsapp_bridge_autopilot send --to 'exact-jid-here' --message 'message here'</bash>\n"
            "- Siri can send WhatsApp messages through iOS/WhatsApp-supported intents; Alice does not automatically inherit Siri's native app permissions."
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
