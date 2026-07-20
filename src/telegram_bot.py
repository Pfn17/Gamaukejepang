import os
import requests
from config import cfg
from src import telegram_commands


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


def get_updates(offset: int = 0):
    if not cfg.TELEGRAM_BOT_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, params={"offset": offset, "timeout": 10}, timeout=15)
        data = resp.json()
        return data.get("result", [])
    except requests.RequestException:
        return []


def process_update(update: dict) -> bool:
    message = update.get("message", {})
    text = (message.get("text") or "").strip()
    chat_id = message.get("chat", {}).get("id")
    if not text or not chat_id:
        return False
    if text.startswith("/"):
        response = telegram_commands.handle_command(text)
        send_to_chat(chat_id, response)
        return True
    return False


def send_to_chat(chat_id: int, text: str, disable_web_page_preview: bool = True) -> bool:
    if not cfg.TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_web_page_preview,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False
