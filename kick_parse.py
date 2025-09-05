# kick_parse.py

import json

# Tell the UI to prompt for a username
INPUT_TYPE = "username"

# The events you can filter in the UI
EVENTS = [
    "Kick chat", "Kick redeem", "Kick follow", "Kick sub", "Kick gift sub",
    "Kick raid start", "Kick raid end", "Kick ban", "Kick timeout",
    "Kick stream start", "Kick stream end", "Kick other"
]

# Human‐friendly labels and templates
TRIGGERS = {
    "Kick chat":         "Kick chat",
    "Kick redeem":       "Kick redeem {title}",
    "Kick follow":       "Kick follow",
    "Kick sub":          "Kick sub",
    "Kick gift sub":     "Kick gift sub",
    "Kick raid start":   "Kick raid start",
    "Kick raid end":     "Kick raid end",
    "Kick ban":          "Kick ban",
    "Kick timeout":      "Kick timeout",
    "Kick stream start": "Kick stream start",
    "Kick stream end":   "Kick stream end",
    "Kick other":        "Kick other ({event})"
}


def get_chat_url(username: str) -> str:
    """
    Kick’s pop-out chat URL.
    """
    # You might need to adjust to /{username}/popout/chat if this one errors
    return f"https://kick.com/popout/{username}/chat"


def try_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def detect_event_name(payload_str: str) -> str | None:
    """
    Scan for any known Kick event type in the raw payload.
    """
    names = [
        "ChatMessageEvent", "RewardRedeemedEvent", "FollowEvent", "SubscriptionEvent",
        "GiftedSubscriptionEvent", "PinnedMessageEvent", "ReactionCreatedEvent",
        "UserBannedEvent", "UserTimedOutEvent", "StreamStartedEvent", "StreamEndedEvent",
        "HostStartedEvent", "HostEndedEvent", "RaidStartedEvent", "RaidEndedEvent",
        "PollStartedEvent", "PollEndedEvent", "PollVoteEvent", "StreamUpdatedEvent",
        "ChatClearedEvent", "EmoteCreatedEvent", "EmoteDeletedEvent"
    ]
    for n in names:
        if n in payload_str:
            return n
    return None


def parse_frame(payload_str: str):
    """
    Called on each WS frame. Returns (event_key, {trigger, customData})
    or None if payload is empty.
    """
    en = detect_event_name(payload_str)
    if not en:
        # no known event → classify as “other”
        return "Kick other", {
            "trigger": TRIGGERS["Kick other"].format(event="Unknown"),
            "customData": {"raw": payload_str}
        }

    # attempt to parse JSON wrapper
    d = try_json(payload_str) or {}
    raw_data = d.get("data")
    if isinstance(raw_data, str):
        inner = try_json(raw_data)
        if isinstance(inner, dict):
            d["data"] = inner

    ek    = "Kick other"
    title = ""
    payload = d if isinstance(d, dict) else {"raw": payload_str}

    if en == "ChatMessageEvent":
        ek = "Kick chat"

    elif en == "RewardRedeemedEvent":
        ek = "Kick redeem"
        rd = {}
        data_field = d.get("data")
        if isinstance(data_field, dict):
            rd = data_field
        elif isinstance(data_field, str):
            parsed = try_json(data_field)
            if isinstance(parsed, dict):
                rd = parsed
        title = (
            (rd.get("reward", {}) or {}).get("title")
            or rd.get("reward_title")
            or rd.get("title")
            or "Unknown"
        )
        payload = rd or {"raw": payload_str}

    elif en == "FollowEvent":
        ek = "Kick follow"
    elif en == "SubscriptionEvent":
        ek = "Kick sub"
    elif en == "GiftedSubscriptionEvent":
        ek = "Kick gift sub"
    elif en == "RaidStartedEvent":
        ek = "Kick raid start"
    elif en == "RaidEndedEvent":
        ek = "Kick raid end"
    elif en == "UserBannedEvent":
        ek = "Kick ban"
    elif en == "UserTimedOutEvent":
        ek = "Kick timeout"
    elif en == "StreamStartedEvent":
        ek = "Kick stream start"
    elif en == "StreamEndedEvent":
        ek = "Kick stream end"

    # build the trigger string
    template = TRIGGERS.get(ek, TRIGGERS["Kick other"])
    trigger = template.format(title=title, event=en)

    return ek, {
        "trigger": trigger,
        "customData": payload
    }


def attach_listeners(page, cdp_session, event_queue, source_id):
    """
    Wire up Kick’s WebSocket frames for this chat context.
    The new driver will invoke this method automatically.
    """
    def _on_ws(frame):
        payload = frame["response"]["payloadData"]
        result  = parse_frame(payload)
        if result:
            ek, fmt = result
            event_queue.put((
                __name__,    # should match parser.__name__
                source_id,
                ek,
                fmt["trigger"],
                fmt["customData"]
            ))

    cdp_session.on("Network.webSocketFrameReceived", _on_ws)