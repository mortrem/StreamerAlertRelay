# 🚨 Streamer Alert Relay

**Streamer Alert Relay** is a modular, real-time event router for streamers. It listens to live chat traffic from platforms like YouTube, Kick, and Twitch, parses it, and dispatches clean triggers to [Sammi](https://sammi.solutions) via its Webhook interface.

Built with Chromium, driven by Playwright, and powered by Python. No cloud. No nonsense. Just raw hooks.

---

## ⚡ Features

- 🧩 Drop-in parser system — just add a `*_parse.py` file and it shows up in the UI  
- 🎯 Real-time trigger dispatch to Sammi via Webhook  
- 🕵️‍♂️ Reverse-engineered support for YouTube’s live chat polling  
- 🧠 Async driver loop with WebSocket and HTTP frame interception  
- 🖥️ Minimal GUI with zone-based configuration  
- 🛡️ Non-commercial, privacy-respecting license  

---

## 🛠 Requirements

- Python 3.10+  
- Playwright (auto-installed on first launch)  
- Chromium (auto-installed into `./playwright_home`)  
- Sammi running locally with Webhook enabled  

---

## 🚀 Getting Started

1. Clone the repo  
2. Run `main.py`  
3. On first launch, accept the Playwright install prompt  
4. Paste a YouTube/Kick/Twitch chat URL into one of the zones  
5. Select filters (e.g. “YouTube Chat”, “Superchat”)  
6. Click **Start**  
7. Watch Sammi react in real time via Webhook triggers  

---

## 🧬 Architecture

- `main.py` — GUI launcher and config manager  
- `driver.py` — async browser controller using Playwright  
- `*_parse.py` — individual platform parsers (e.g. `youtube_parse.py`)  
- `sammi.py` — Webhook dispatcher to Sammi  

Each parser defines:
```python
EVENTS = ["chat_message", "paid_message"]
TRIGGERS = {"chat_message": "YouTube Chat", ...}
def get_chat_url(input): ...
def parse_frame(payload): ...
def attach_listeners(page, cdp, queue, source_id): ...
