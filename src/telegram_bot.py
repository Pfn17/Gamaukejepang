import os
import requests
from config import cfg


def _dashboard_url() -> str:
    base = os.getenv("DASHBOARD_URL", "http://localhost:5000")
    return base.rstrip("/")


def send_message(text: str, disable_web_page_preview: bool = True) -> bool:
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        payload_text = text
        if "dashboard" not in payload_text.lower() and _dashboard_url():
            payload_text = f"{payload_text}\n\nDashboard: {_dashboard_url()}"
        resp = requests.post(
            url,
            json={
                "chat_id": cfg.TELEGRAM_CHAT_ID,
                "text": payload_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_web_page_preview,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False
