import requests
from app.config import settings


class TelegramService:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    def send_message(self, text: str) -> dict:
        if not self.bot_token or not self.chat_id:
            return {"ok": False, "message": "Telegram não configurado"}

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    def send_photo(self, photo_url: str, caption: str = "") -> dict:
        if not self.bot_token or not self.chat_id:
            return {"ok": False, "message": "Telegram não configurado"}

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "Markdown",
        }

        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        return response.json()