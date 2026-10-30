"""Exportable Bolna agent tool definitions + safety prompt for REDEEM.

Usage:  python -m app.voice.agent_config https://your-host  <webhook-secret>  > redeem-agent-tools.json
Status: shaped after a working Bolna agent observed in another project (custom functions with flat string parameters;
Bolna substitutes {execution_id}). NOT yet applied to or verified against a live Bolna account.
"""
import json
import sys

STR = {"type": "string"}


def _tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": description, "pre_call_message": "Okay.",
            "parameters": {"type": "object", "properties": {"execution_id": {**STR, "description": "This call's reference. Always use the value from your instructions."}, **props},
                           "required": ["execution_id", *required]}}


TOOLS = [
    _tool("start_mission", "Start a REDEEM mission from what the caller wants. Call once the caller has stated their problem. It only plans; the caller must approve in the app.",
          {"intent": {**STR, "description": "The caller's request in their own words. Keep names and booking references exactly as spoken."}}, ["intent"]),
    _tool("mission_reply", "Apply the caller's follow-up to the current mission: pick 'the second option', name an item, or correct an earlier instruction.",
          {"text": {**STR, "description": "The caller's latest instruction, verbatim."}}, ["text"]),
    _tool("read_back_plan", "Get the spoken summary of the next action awaiting approval, including the affected account and the consequence. Read it out exactly.", {}, []),
    _tool("interrupt", "Call immediately when the caller says stop or wait or interrupts an action. Pauses the mission so nothing stale runs.", {}, []),
    _tool("search_catalogue", "Look up products and live stock in the shop catalogue.", {"query": {**STR, "description": "Product words, e.g. keyboard."}}, ["query"]),
    _tool("lookup_booking", "Look up the status of a booking by its reference.", {"ref": {**STR, "description": "Booking reference exactly as spoken, e.g. FA2041."}}, ["ref"]),
]

PROMPT = """You are REDEEM's voice assistant. At the start say you are an AI assistant. Never ask for or accept OTPs, PINs, CVVs or passwords; if the caller says someone asked for one, tell them it is a scam.
You cannot approve, pay, cancel or book anything by voice. For any change: call read_back_plan, read the summary exactly, and tell the caller to approve it in the REDEEM app.
Identify customers and bookings by reference or phone suffix, never by name alone; if two match, ask. If the caller interrupts or corrects you, call interrupt, then mission_reply.
Never invent availability, prices, refund status or legal rights: use the tools. If a tool fails, say so. Keep the caller's language; names and references stay unchanged."""


def build(base_url: str, secret: str) -> dict:
    base = base_url.rstrip("/")
    return {"agent_prompt": PROMPT, "tools": [
        {**t, "url": f"{base}/api/v1/voice/tools/{t['name']}?token={secret}", "method": "POST",
         "param_values": {"execution_id": "{execution_id}"}} for t in TOOLS],
        "webhook_url": f"{base}/api/v1/webhooks/bolna?token={secret}",
        "status": "UNVERIFIED_AGAINST_LIVE_BOLNA"}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1] if len(sys.argv) > 1 else "https://example.invalid", sys.argv[2] if len(sys.argv) > 2 else "<secret>"), indent=2, ensure_ascii=False))
