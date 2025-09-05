# twitch_parse.py

import json

# prompt the UI to show “Enter username”
INPUT_TYPE = "username"

# events available for filtering
EVENTS = [
    "Twitch chat",
    "Twitch redeem (irc)",
    "Twitch redeem (pubsub)",
    "Twitch sub",
    "Twitch raid",
    "Twitch ban",
    "Twitch timeout",
    "Twitch message delete",
    "Twitch notice",
    "Twitch roomstate",
    "Twitch other"
]

# human-friendly labels and templates
TRIGGERS = {
    "Twitch chat":            "Twitch chat",
    "Twitch redeem (irc)":    "Twitch redeem {short_id}",
    "Twitch redeem (pubsub)": "Twitch redeem {title}",
    "Twitch sub":             "Twitch sub",
    "Twitch raid":            "Twitch raid",
    "Twitch ban":             "Twitch ban",
    "Twitch timeout":         "Twitch timeout",
    "Twitch message delete":  "Twitch message delete",
    "Twitch notice":          "Twitch notice",
    "Twitch roomstate":       "Twitch roomstate",
    "Twitch other":           "Twitch other ({command})"
}


def get_chat_url(channel: str) -> str:
    """
    Return Twitch’s pop-out chat URL for the given channel.
    """
    return f"https://www.twitch.tv/popout/{channel}/chat?popout="


def try_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def parse_irc_tags(tag_str: str) -> dict:
    tags = {}
    if not tag_str:
        return tags
    for part in tag_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            # unescape IRC tag values
            v = (v.replace(r"\:", ";")
                  .replace(r"\s", " ")
                  .replace(r"\\", "\\")
                  .replace(r"\r", "\r")
                  .replace(r"\n", "\n"))
            tags[k] = v
        else:
            tags[part] = True
    return tags


def parse_irc_line(line: str) -> dict | None:
    rest = line.strip()
    if not rest or rest.startswith("PING"):
        return None

    tags = {}
    prefix = None
    text = None

    if rest.startswith("@"):
        i = rest.find(" ")
        tags = parse_irc_tags(rest[1:i])
        rest = rest[i+1:].lstrip()

    if rest.startswith(":"):
        i = rest.find(" ")
        prefix = rest[1:i]
        rest = rest[i+1:].lstrip()

    ti = rest.find(" :")
    if ti != -1:
        text = rest[ti+2:]
        rest = rest[:ti].strip()

    parts = rest.split()
    if not parts:
        return None

    return {
        "tags": tags,
        "prefix": prefix,
        "command": parts[0],
        "params": parts[1:],
        "text": text
    }


def nick_from_prefix(prefix: str) -> str | None:
    if not prefix:
        return None
    i = prefix.find("!")
    return prefix[:i] if i != -1 else prefix


def param_channel(params: list[str]) -> str | None:
    if not params:
        return None
    ch = params[0]
    return ch[1:] if ch.startswith("#") else ch


def build_payload_from_irc(msg: dict) -> dict:
    tags = msg.get("tags", {})
    return {
        "source":       "irc",
        "command":      msg.get("command"),
        "channel":      param_channel(msg.get("params", [])),
        "text":         msg.get("text"),
        "prefix":       msg.get("prefix"),
        "nick":         nick_from_prefix(msg.get("prefix")),
        "tags":         tags,
        "display_name": tags.get("display-name") or nick_from_prefix(msg.get("prefix")),
        "user_id":      tags.get("user-id"),
        "room_id":      tags.get("room-id"),
        "msg_id":       tags.get("id"),
    }


def parse_frame(payload_str: str):
    # Try PubSub JSON first
    j = try_json(payload_str)
    if isinstance(j, dict) and "notification" in j:
        notif = j["notification"]
        blob  = notif.get("pubsub")
        inner = (blob if isinstance(blob, dict)
                 else try_json(blob) if isinstance(blob, str)
                 else None)
        if isinstance(inner, dict):
            t = inner.get("type", "")
            if t == "reward-redeemed":
                data = inner.get("data", {})
                red  = data.get("redemption", {}) if isinstance(data, dict) else {}
                user = red.get("user", {}) if isinstance(red, dict) else {}
                reward = red.get("reward", {}) if isinstance(red, dict) else {}
                title = reward.get("title") or "Unknown"
                payload = {
                    "source":             "pubsub",
                    "event":              "reward-redeemed",
                    "timestamp":          data.get("timestamp"),
                    "redeemed_at":        red.get("redeemed_at"),
                    "channel_id":         red.get("channel_id"),
                    "user_display_name":  user.get("display_name"),
                    "user_login":         user.get("login"),
                    "user_id":            user.get("id"),
                    "reward_title":       title,
                    "reward_id":          reward.get("id"),
                }
                trig = TRIGGERS["Twitch redeem (pubsub)"].format(title=title)
                return "Twitch redeem (pubsub)", {"trigger": trig, "customData": payload}
            else:
                trig = TRIGGERS["Twitch other"].format(command=t)
                return "Twitch other", {"trigger": trig, "customData": inner}

    # Fallback to IRC parsing
    for line in payload_str.split("\r\n"):
        msg = parse_irc_line(line)
        if not msg:
            continue

        cmd = msg["command"]
        tags = msg.get("tags", {})
        payload = build_payload_from_irc(msg)

        if cmd == "PRIVMSG" and "custom-reward-id" in tags:
            short_id = tags["custom-reward-id"][:6] + "…" if tags.get("custom-reward-id") else ""
            trig = TRIGGERS["Twitch redeem (irc)"].format(short_id=short_id)
            return "Twitch redeem (irc)", {"trigger": trig, "customData": payload}

        if cmd == "PRIVMSG":
            trig = TRIGGERS["Twitch chat"]
            return "Twitch chat", {"trigger": trig, "customData": payload}

        if cmd == "USERNOTICE":
            mid = tags.get("msg-id", "")
            if mid in ("sub", "resub", "subgift", "anonsubgift", "submysterygift"):
                trig = TRIGGERS["Twitch sub"]
                return "Twitch sub", {"trigger": trig, "customData": payload}
            if mid == "raid":
                trig = TRIGGERS["Twitch raid"]
                return "Twitch raid", {"trigger": trig, "customData": payload}
            trig = TRIGGERS["Twitch notice"]
            return "Twitch notice", {"trigger": trig, "customData": payload}

        if cmd == "CLEARCHAT":
            if "ban-duration" in tags:
                trig = TRIGGERS["Twitch timeout"]
                return "Twitch timeout", {"trigger": trig, "customData": payload}
            trig = TRIGGERS["Twitch ban"]
            return "Twitch ban", {"trigger": trig, "customData": payload}

        if cmd == "CLEARMSG":
            trig = TRIGGERS["Twitch message delete"]
            return "Twitch message delete", {"trigger": trig, "customData": payload}

        if cmd == "NOTICE":
            trig = TRIGGERS["Twitch notice"]
            return "Twitch notice", {"trigger": trig, "customData": payload}

        if cmd == "ROOMSTATE":
            trig = TRIGGERS["Twitch roomstate"]
            return "Twitch roomstate", {"trigger": trig, "customData": payload}

        # any other IRC command
        trig = TRIGGERS["Twitch other"].format(command=cmd)
        return "Twitch other", {"trigger": trig, "customData": payload}

    # if nothing matched, emit raw
    return "Twitch other", {
        "trigger": TRIGGERS["Twitch other"].format(command="Unknown"),
        "customData": {"raw": payload_str}
    }


def attach_listeners(page, cdp_session, event_queue, source_id):
    """
    Hook Twitch’s WebSocket frames for this chat context.
    The driver will call this automatically.
    """
    def _ws_handler(frame):
        payload = frame["response"]["payloadData"]
        result  = parse_frame(payload)
        if result:
            ek, fmt = result
            event_queue.put((
                __name__,
                source_id,
                ek,
                fmt["trigger"],
                fmt["customData"]
            ))

    cdp_session.on("Network.webSocketFrameReceived", _ws_handler)