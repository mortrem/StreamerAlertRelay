# youtube_parse.py

import re
import json
from urllib.parse import urlparse, parse_qs

# UI will prompt “Enter url”
INPUT_TYPE = "url"

# filter keys
EVENTS = [
    "chat_message",
    "paid_message",
    "raw_json"
]

# static labels for the UI checkboxes and triggers
TRIGGERS = {
    "chat_message": "YouTube Chat",
    "paid_message": "YouTube Superchat",
    "raw_json":     "Raw JSON"
}


def get_chat_url(input_str: str) -> str:
    if "studio.youtube.com/live_chat" in input_str:
        parsed = urlparse(input_str)
        vid = parse_qs(parsed.query).get("v", [""])[0]
        return f"https://www.youtube.com/live_chat?is_popout=1&v={vid}"
    if "youtube.com/live_chat" in input_str:
        if "is_popout=1" not in input_str:
            sep = "&" if "?" in input_str else "?"
            return input_str + f"{sep}is_popout=1"
        return input_str
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", input_str)
    vid = m.group(1) if m else input_str.strip()
    return f"https://www.youtube.com/live_chat?is_popout=1&v={vid}"


def parse_frame(payload_str: str):
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        return (
            "raw_json",
            {
                "trigger": TRIGGERS["raw_json"],
                "customData": {"raw": payload_str}
            }
        )

    actions = data.get("actions", []) or \
        data.get("continuationContents", {}) \
            .get("liveChatContinuation", {}) \
            .get("actions", [])

    for action in actions:
        item = action.get("addChatItemAction", {}).get("item", {})

        if "liveChatTextMessageRenderer" in item:
            r      = item["liveChatTextMessageRenderer"]
            author = r.get("authorName", {}).get("simpleText", "")
            runs   = r.get("message", {}).get("runs", [])
            text   = "".join(run.get("text", "") for run in runs)

            return (
                "chat_message",
                {
                    "trigger": TRIGGERS["chat_message"],
                    "customData": {"author": author, "text": text}
                }
            )

        if "liveChatPaidMessageRenderer" in item:
            r      = item["liveChatPaidMessageRenderer"]
            author = r.get("authorName", {}).get("simpleText", "")
            amount = r.get("purchaseAmountText", {}).get("simpleText", "")
            runs   = r.get("message", {}).get("runs", [])
            text   = "".join(run.get("text", "") for run in runs)

            return (
                "paid_message",
                {
                    "trigger": TRIGGERS["paid_message"],
                    "customData": {"author": author, "amount": amount, "text": text}
                }
            )

    return (
        "raw_json",
        {
            "trigger": TRIGGERS["raw_json"],
            "customData": data
        }
    )


def attach_listeners(page, cdp_session, event_queue, source_id):
    async def _on_response(resp):
        if "get_live_chat" not in resp.url:
            return
        try:
            body = await resp.text()
            ek, fmt = parse_frame(body)
            event_queue.put((
                __name__,     # "youtube_parse"
                source_id,
                ek,
                fmt["trigger"],
                fmt["customData"]
            ))
        except:
            pass

    page.on("response", _on_response)