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
    _tool("computer_task", "Do a task on the caller's connected computer (REDEEM operates the real screen with mouse and keyboard). Pass the caller's request in their words.", {"instruction": {**STR, "description": "What to do on the computer."}}, ["instruction"]),
    _tool("computer_status", "Read the progress or the final result of the current computer task. Read the 'say' field to the caller. If it has an approval, read 'describe' and ask for a clear yes.", {}, []),
    _tool("computer_control", "Pause, continue, stop, take over (the caller wants to use the computer) or hand back control.", {"op": {**STR, "description": "pause | continue | stop | take over | hand back"}}, ["op"]),
    _tool("computer_approve", "Approve the exact action computer_status described, only after the caller clearly said yes to it.", {"digest": {**STR, "description": "approval.digest from computer_status"}, "confirmed": {**STR, "description": "true only if the caller said yes"}}, ["digest", "confirmed"]),
    _tool("save_answer", "Save what the caller just told you (a preference or detail) to their private memory. Pass the caller's exact words, and the field you asked about if any (e.g. travel.seat_preference). If the result has ask_user, ask that question and do not save anything yet.", {"utterance": {**STR, "description": "The caller's exact words."}, "field": {**STR, "description": "Field you just asked about, if any."}}, ["utterance"]),
    _tool("recall", "Read the caller's CONFIRMED saved preferences relevant to a topic, so you do not ask again.", {"topic": {**STR, "description": "e.g. flight refund."}}, []),
]

PROMPT = """You are REDEEM's voice assistant. At the start say you are an AI assistant. Never ask for or accept OTPs, PINs, CVVs or passwords; if the caller says someone asked for one, tell them it is a scam.
You cannot approve, pay, cancel or book anything by voice. For any change: call read_back_plan, read the summary exactly, and tell the caller to approve it in the REDEEM app.
Identify customers and bookings by reference or phone suffix, never by name alone; if two match, ask. If the caller interrupts or corrects you, call interrupt, then mission_reply.
When the caller states a preference, call save_answer; if it returns ask_user, ask exactly that. Before asking for details, call recall. Only confirmed memory is returned.
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
