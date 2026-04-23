import re
import requests
from typing import Optional, Dict, Any, List

from app.config import settings
from app.services.runtime_config_service import load_runtime_config


class TelegramService:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.channel_chat_id = getattr(settings, "telegram_channel_chat_id", "")

    # ---------------------------------------------------------------------
    # CONFIG / DESTINOS
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # MARKDOWN / SANITIZAÇÃO
    # ---------------------------------------------------------------------
    def _escape_markdown_v2(self, text: str) -> str:
        if text is None:
            return ""
        text = str(text)
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{ch}" if ch in escape_chars else ch for ch in text)

    def _strip_markdown_v2(self, text: str) -> str:
        if not text:
            return ""

        cleaned = str(text)

        cleaned = re.sub(r"\\([_*$begin:math:display$$end:math:display$()~`>#+\-=|{}.!])", r"\1", cleaned)
        cleaned = cleaned.replace("*", "")
        cleaned = cleaned.replace("_", "")
        cleaned = cleaned.replace("`", "")

        return cleaned

    # ---------------------------------------------------------------------
    # HTTP POST
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # ENVIO BÁSICO
    # ---------------------------------------------------------------------
    def _send_message_to_chat(self, chat_id: str, text: str, label: str) -> dict:
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

        fallback_caption = self._strip_markdown_v2(caption)
        fallback_payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": fallback_caption[:1024],
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

    # ---------------------------------------------------------------------
    # FORMATADORES
    # ---------------------------------------------------------------------
    def _format_percent(self, value: Optional[float]) -> str:
        try:
            if value is None:
                return "-"
            return f"{float(value) * 100:.2f}%"
        except Exception:
            return "-"

    def _format_odd(self, value: Optional[float]) -> str:
        try:
            if value is None:
                return "-"
            return f"{float(value):.2f}"
        except Exception:
            return "-"

    def _format_edge(self, value: Optional[float]) -> str:
        try:
            if value is None:
                return "-"
            return f"{float(value):.2f}%"
        except Exception:
            return "-"

    def _market_label(self, market_type: Optional[str]) -> str:
        text = str(market_type or "").strip().lower()

        if text in {"double_chance", "dupla_hipotese", "dupla hipótese"}:
            return "Dupla hipótese"

        if text in {"1x2", "match_winner"}:
            return "1x2"

        return "Mercado"

    def _pick_label(self, pick: Optional[str], market_type: Optional[str] = None) -> str:
        pick = str(pick or "").strip().upper()

        if market_type in {"double_chance", "dupla_hipotese", "dupla hipótese"}:
            mapping = {
                "1X": "Casa ou Empate",
                "X2": "Empate ou Fora",
                "12": "Casa ou Fora",
            }
            return mapping.get(pick, pick or "-")

        mapping = {
            "1": "Casa",
            "X": "Empate",
            "2": "Fora",
            "1X": "Casa ou Empate",
            "X2": "Empate ou Fora",
            "12": "Casa ou Fora",
        }
        return mapping.get(pick, pick or "-")

    # ---------------------------------------------------------------------
    # MENSAGEM DE PREVISÃO
    # ---------------------------------------------------------------------
    def build_prediction_message(self, payload: Dict[str, Any]) -> str:
        league = str(payload.get("league_name") or payload.get("league") or "Liga").strip()
        home_team = str(payload.get("home_team") or "Time A").strip()
        away_team = str(payload.get("away_team") or "Time B").strip()
        match_date = str(payload.get("match_date") or payload.get("date") or "-").strip()
        match_time = str(payload.get("match_time") or payload.get("time") or "-").strip()

        market_type = str(payload.get("market_type") or "1x2").strip()
        suggested_pick = str(payload.get("suggested_pick") or payload.get("pick") or "-").strip().upper()
        confidence = str(payload.get("confidence") or "baixa").strip()
        model_source = str(payload.get("model_source") or "-").strip()

        prob_home = payload.get("prob_home")
        prob_draw = payload.get("prob_draw")
        prob_away = payload.get("prob_away")

        prob_1x = payload.get("prob_1x")
        prob_x2 = payload.get("prob_x2")
        prob_12 = payload.get("prob_12")

        odds = payload.get("odds") or {}
        fair_odds = payload.get("fair_odds") or {}
        value_bet = payload.get("value_bet") or {}

        bookmaker = odds.get("bookmaker") or "-"

        lines = [
            "🚨 *Nova previsão detectada*",
            "",
            f"🏆 *Liga:* {self._escape_markdown_v2(league)}",
            f"⚽ *Jogo:* {self._escape_markdown_v2(home_team)} x {self._escape_markdown_v2(away_team)}",
            f"🗓️ *Data:* {self._escape_markdown_v2(match_date)}",
            f"⏰ *Hora:* {self._escape_markdown_v2(match_time)}",
            "",
            f"📌 *Mercado:* {self._escape_markdown_v2(self._market_label(market_type))}",
            f"🎯 *Pick:* {self._escape_markdown_v2(self._pick_label(suggested_pick, market_type))}",
            f"🔥 *Confiança:* {self._escape_markdown_v2(confidence.capitalize())}",
            f"🧠 *Fonte:* {self._escape_markdown_v2(model_source)}",
            "",
            "📊 *Probabilidades:*",
            f"• Casa: {self._escape_markdown_v2(self._format_percent(prob_home))}",
            f"• Empate: {self._escape_markdown_v2(self._format_percent(prob_draw))}",
            f"• Fora: {self._escape_markdown_v2(self._format_percent(prob_away))}",
        ]

        if prob_1x is not None or prob_x2 is not None or prob_12 is not None:
            lines.extend([
                "",
                "🛡️ *Dupla hipótese:*",
                f"• 1X: {self._escape_markdown_v2(self._format_percent(prob_1x))}",
                f"• X2: {self._escape_markdown_v2(self._format_percent(prob_x2))}",
                f"• 12: {self._escape_markdown_v2(self._format_percent(prob_12))}",
            ])

        lines.extend([
            "",
            "💸 *Odds de mercado:*",
            f"• Casa: {self._escape_markdown_v2(self._format_odd(odds.get('home_odds')))}",
            f"• Empate: {self._escape_markdown_v2(self._format_odd(odds.get('draw_odds')))}",
            f"• Fora: {self._escape_markdown_v2(self._format_odd(odds.get('away_odds')))}",
            f"• 1X: {self._escape_markdown_v2(self._format_odd(odds.get('odds_1x')))}",
            f"• X2: {self._escape_markdown_v2(self._format_odd(odds.get('odds_x2')))}",
            f"• 12: {self._escape_markdown_v2(self._format_odd(odds.get('odds_12')))}",
            f"• Bookmaker: {self._escape_markdown_v2(bookmaker)}",
        ])

        if fair_odds:
            lines.extend([
                "",
                "📐 *Odds justas:*",
                f"• 1: {self._escape_markdown_v2(self._format_odd(fair_odds.get('1')))}",
                f"• X: {self._escape_markdown_v2(self._format_odd(fair_odds.get('X')))}",
                f"• 2: {self._escape_markdown_v2(self._format_odd(fair_odds.get('2')))}",
                f"• 1X: {self._escape_markdown_v2(self._format_odd(fair_odds.get('1X')))}",
                f"• X2: {self._escape_markdown_v2(self._format_odd(fair_odds.get('X2')))}",
                f"• 12: {self._escape_markdown_v2(self._format_odd(fair_odds.get('12')))}",
            ])

        if value_bet:
            lines.extend([
                "",
                "💎 *Value bet:*",
                f"• Tem valor: {self._escape_markdown_v2('Sim' if value_bet.get('has_value') else 'Não')}",
                f"• Edge: {self._escape_markdown_v2(self._format_edge(value_bet.get('edge')))}",
            ])

        return "\n".join(lines)

    def send_prediction_alert(self, payload: Dict[str, Any]) -> dict:
        text = self.build_prediction_message(payload)
        return self.send_message(text)

    # ---------------------------------------------------------------------
    # MENSAGEM LIVE
    # ---------------------------------------------------------------------
    def build_live_message(self, payload: Dict[str, Any]) -> str:
        league = str(payload.get("league") or payload.get("league_name") or "Liga").strip()
        home_team = str(payload.get("home_team") or "Time A").strip()
        away_team = str(payload.get("away_team") or "Time B").strip()

        home_score = payload.get("home_score")
        away_score = payload.get("away_score")
        status_text = str(payload.get("status_text") or "Ao vivo").strip()
        pick = str(payload.get("pick") or "-").strip().upper()
        confidence = str(payload.get("confidence") or "-").strip()

        message = [
            "🔴 *Atualização ao vivo*",
            "",
            f"🏆 *Liga:* {self._escape_markdown_v2(league)}",
            f"⚽ *Jogo:* {self._escape_markdown_v2(home_team)} x {self._escape_markdown_v2(away_team)}",
            f"📟 *Status:* {self._escape_markdown_v2(status_text)}",
            f"🥅 *Placar:* {self._escape_markdown_v2(str(home_score if home_score is not None else '-'))} x {self._escape_markdown_v2(str(away_score if away_score is not None else '-'))}",
            f"🎯 *Pick enviado:* {self._escape_markdown_v2(self._pick_label(pick))}",
            f"🔥 *Confiança:* {self._escape_markdown_v2(confidence.capitalize() if confidence else '-')}",
        ]

        return "\n".join(message)

    def send_live_alert(self, payload: Dict[str, Any]) -> dict:
        text = self.build_live_message(payload)
        return self.send_message(text)

    # ---------------------------------------------------------------------
    # MENSAGEM DE GOL
    # ---------------------------------------------------------------------
    def build_goal_message(self, payload: Dict[str, Any]) -> str:
        league = str(payload.get("league") or payload.get("league_name") or "Liga").strip()
        home_team = str(payload.get("home_team") or "Time A").strip()
        away_team = str(payload.get("away_team") or "Time B").strip()
        home_score = payload.get("home_score")
        away_score = payload.get("away_score")
        status_text = str(payload.get("status_text") or "Ao vivo").strip()

        lines = [
            "⚽ *Gol na partida\\!*",
            "",
            f"🏆 *Liga:* {self._escape_markdown_v2(league)}",
            f"⚽ *Jogo:* {self._escape_markdown_v2(home_team)} x {self._escape_markdown_v2(away_team)}",
            f"📟 *Status:* {self._escape_markdown_v2(status_text)}",
            f"🥅 *Novo placar:* {self._escape_markdown_v2(str(home_score if home_score is not None else '-'))} x {self._escape_markdown_v2(str(away_score if away_score is not None else '-'))}",
        ]

        return "\n".join(lines)

    def send_goal_alert(self, payload: Dict[str, Any]) -> dict:
        text = self.build_goal_message(payload)
        return self.send_message(text)

    # ---------------------------------------------------------------------
    # MENSAGEM PRÉ-JOGO
    # ---------------------------------------------------------------------
    def build_pre_match_message(self, payload: Dict[str, Any]) -> str:
        league = str(payload.get("league") or payload.get("league_name") or "Liga").strip()
        home_team = str(payload.get("home_team") or "Time A").strip()
        away_team = str(payload.get("away_team") or "Time B").strip()
        match_date = str(payload.get("match_date") or payload.get("date") or "-").strip()
        match_time = str(payload.get("match_time") or payload.get("time") or "-").strip()
        pick = str(payload.get("pick") or payload.get("suggested_pick") or "-").strip().upper()
        confidence = str(payload.get("confidence") or "-").strip()
        market_type = str(payload.get("market_type") or "1x2").strip()

        lines = [
            "⏳ *Jogo começando em breve*",
            "",
            f"🏆 *Liga:* {self._escape_markdown_v2(league)}",
            f"⚽ *Jogo:* {self._escape_markdown_v2(home_team)} x {self._escape_markdown_v2(away_team)}",
            f"🗓️ *Data:* {self._escape_markdown_v2(match_date)}",
            f"⏰ *Hora:* {self._escape_markdown_v2(match_time)}",
            f"📌 *Mercado:* {self._escape_markdown_v2(self._market_label(market_type))}",
            f"🎯 *Pick:* {self._escape_markdown_v2(self._pick_label(pick, market_type))}",
            f"🔥 *Confiança:* {self._escape_markdown_v2(confidence.capitalize() if confidence else '-')}",
        ]

        return "\n".join(lines)

    def send_pre_match_alert(self, payload: Dict[str, Any]) -> dict:
        text = self.build_pre_match_message(payload)
        return self.send_message(text)

    # ---------------------------------------------------------------------
    # RESUMO LIVE
    # ---------------------------------------------------------------------
    def build_live_summary_message(self, matches: List[Dict[str, Any]]) -> str:
        if not matches:
            return "📡 *Resumo live*\n\nNenhuma partida ao vivo monitorada no momento\\."

        lines = [
            "📡 *Resumo live das partidas*",
            "",
        ]

        for item in matches[:10]:
            home_team = str(item.get("home_team") or "Time A").strip()
            away_team = str(item.get("away_team") or "Time B").strip()
            home_score = item.get("home_score")
            away_score = item.get("away_score")
            status_text = str(item.get("status_text") or item.get("last_status_text") or "Ao vivo").strip()
            pick = str(item.get("pick") or "-").strip().upper()

            lines.append(
                f"• {self._escape_markdown_v2(home_team)} x {self._escape_markdown_v2(away_team)} "
                f"\\| {self._escape_markdown_v2(str(home_score if home_score is not None else '-'))}"
                f"x{self._escape_markdown_v2(str(away_score if away_score is not None else '-'))} "
                f"\\| {self._escape_markdown_v2(status_text)} "
                f"\\| Pick: {self._escape_markdown_v2(self._pick_label(pick))}"
            )

        return "\n".join(lines)

    def send_live_summary(self, matches: List[Dict[str, Any]]) -> dict:
        text = self.build_live_summary_message(matches)
        return self.send_message(text)