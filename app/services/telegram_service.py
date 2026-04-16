import re
import requests

from app.config import settings
from app.services.runtime_config_service import load_runtime_config


class TelegramService:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.channel_chat_id = getattr(settings, "telegram_channel_chat_id", "")

    def _runtime(self) -> dict:
        try:
            return load_runtime_config() or {}
        except Exception as e:
            print(f"[TELEGRAM] Erro ao carregar runtime config: {e}")
            return {}

    def _is_configured(self) -> bool:
        return bool(self.bot_token)

    def _normalize_chat_id(self, value) -> str:
        return str(value or "").strip()

    def _deduplicate_targets(self, targets: list[dict]) -> list[dict]:
        unique = []
        seen = set()

        for item in targets:
            chat_id = self._normalize_chat_id(item.get("chat_id"))
            if not chat_id:
                continue

            if chat_id in seen:
                continue

            seen.add(chat_id)
            unique.append(
                {
                    "chat_id": chat_id,
                    "label": item.get("label") or chat_id,
                }
            )

        return unique

    def _resolve_targets(self) -> list[dict]:
        runtime = self._runtime()

        send_to_main = bool(runtime.get("telegram_send_to_main_chat", True))
        send_to_channel = bool(runtime.get("telegram_send_to_channel", False))

        targets = []

        if send_to_main and self._normalize_chat_id(self.chat_id):
            targets.append(
                {
                    "chat_id": self.chat_id,
                    "label": "main_chat",
                }
            )

        if send_to_channel and self._normalize_chat_id(self.channel_chat_id):
            targets.append(
                {
                    "chat_id": self.channel_chat_id,
                    "label": "channel",
                }
            )

        return self._deduplicate_targets(targets)

    def _strip_markdown_v2(self, text: str) -> str:
        if not text:
            return ""

        cleaned = str(text)

        # remove escapes comuns do MarkdownV2
        cleaned = re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!])", r"\1", cleaned)

        # remove destaques simples restantes
        cleaned = cleaned.replace("*", "")
        cleaned = cleaned.replace("_", "")
        cleaned = cleaned.replace("`", "")

        return cleaned

    def _post(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"

        try:
            response = requests.post(url, json=payload, timeout=20)

            if response.status_code >= 400:
                body = ""
                try:
                    body = response.text
                except Exception:
                    body = "<sem body>"

                print(
                    f"[TELEGRAM] Erro HTTP {response.status_code} em {method} | "
                    f"payload_keys={list(payload.keys())} | body={body}"
                )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            print(f"[TELEGRAM] Falha no POST {method}: {e}")
            raise

    def _send_message_to_chat(self, chat_id: str, text: str, label: str) -> dict:
        # 1ª tentativa: MarkdownV2
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }

        try:
            result = self._post("sendMessage", payload)
            print(f"[TELEGRAM] Mensagem enviada com MarkdownV2 | destino={label}")
            return result
        except Exception as e:
            print(
                f"[TELEGRAM] Falha com MarkdownV2 | destino={label} | erro={e} | "
                f"tentando fallback texto puro"
            )

        # 2ª tentativa: sem parse_mode
        fallback_text = self._strip_markdown_v2(text)
        fallback_payload = {
            "chat_id": chat_id,
            "text": fallback_text,
            "disable_web_page_preview": True,
        }

        result = self._post("sendMessage", fallback_payload)
        print(f"[TELEGRAM] Mensagem enviada com fallback plain text | destino={label}")
        return result

    def _send_photo_to_chat(self, chat_id: str, photo_url: str, caption: str, label: str) -> dict:
        # 1ª tentativa: MarkdownV2
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "MarkdownV2",
        }

        try:
            result = self._post("sendPhoto", payload)
            print(f"[TELEGRAM] Foto enviada com MarkdownV2 | destino={label}")
            return result
        except Exception as e:
            print(
                f"[TELEGRAM] Falha sendPhoto com MarkdownV2 | destino={label} | erro={e} | "
                f"tentando fallback"
            )

        # 2ª tentativa: caption sem parse_mode
        fallback_caption = self._strip_markdown_v2(caption)
        fallback_payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": fallback_caption[:1024],  # limite do Telegram
        }

        result = self._post("sendPhoto", fallback_payload)
        print(f"[TELEGRAM] Foto enviada com fallback plain text | destino={label}")
        return result

    def send_message(self, text: str) -> dict:
        if not self._is_configured():
            return {"ok": False, "message": "Telegram não configurado"}

        targets = self._resolve_targets()
        if not targets:
            return {"ok": False, "message": "Nenhum destino Telegram habilitado"}

        results = []
        success_count = 0

        for target in targets:
            chat_id = target["chat_id"]
            label = target["label"]

            try:
                result = self._send_message_to_chat(chat_id, text, label)
                results.append(
                    {
                        "label": label,
                        "chat_id": chat_id,
                        "ok": True,
                        "result": result,
                    }
                )
                success_count += 1
            except Exception as e:
                results.append(
                    {
                        "label": label,
                        "chat_id": chat_id,
                        "ok": False,
                        "error": str(e),
                    }
                )

        return {
            "ok": success_count > 0,
            "sent_count": success_count,
            "total_targets": len(targets),
            "results": results,
        }

    def send_photo(self, photo_url: str, caption: str = "") -> dict:
        if not self._is_configured():
            return {"ok": False, "message": "Telegram não configurado"}

        targets = self._resolve_targets()
        if not targets:
            return {"ok": False, "message": "Nenhum destino Telegram habilitado"}

        results = []
        success_count = 0

        for target in targets:
            chat_id = target["chat_id"]
            label = target["label"]

            try:
                result = self._send_photo_to_chat(chat_id, photo_url, caption, label)
                results.append(
                    {
                        "label": label,
                        "chat_id": chat_id,
                        "ok": True,
                        "result": result,
                    }
                )
                success_count += 1
            except Exception as e:
                results.append(
                    {
                        "label": label,
                        "chat_id": chat_id,
                        "ok": False,
                        "error": str(e),
                    }
                )

        return {
            "ok": success_count > 0,
            "sent_count": success_count,
            "total_targets": len(targets),
            "results": results,
        }