import requests

SAMMI_WEBHOOK_URL = "http://localhost:9450/webhook"
SAMMI_PASSWORD = None  # Set this if your SAMMI webhook requires authorization

def send_to_sammi(payload):
    """
    Sends a JSON payload to the SAMMI webhook.
    Expected format:
    {
        "trigger": "EventName",
        "customData": { ... }
    }
    """
    if not isinstance(payload, dict):
        print("[SAMMI] Invalid payload: not a dictionary")
        return

    headers = {"Content-Type": "application/json"}
    if SAMMI_PASSWORD:
        headers["Authorization"] = SAMMI_PASSWORD

    try:
        response = requests.post(SAMMI_WEBHOOK_URL, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            print(f"[SAMMI] Trigger sent: {payload.get('trigger')}")
        else:
            print(f"[SAMMI] Failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[SAMMI] Error sending trigger: {e}")