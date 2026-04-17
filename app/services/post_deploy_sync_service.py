from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Set, Optional

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.prediction_store import (
    save_prediction,
    get_pending_predictions,
)
from app.services.result_checker_service import ResultCheckerService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import format_prediction_message
from app.services.scheduler_service import (
    _already_sent_alert,
    _save_sent_alert,
)


class PostDeploySyncService:
    STARTUP_ALERT_WINDOW_MIN = -10
    STARTUP_ALERT_WINDOW_MAX = 35

    def __init__(self):
        self.daily_service = DailyLeaguesService()
        self.result_checker = ResultCheckerService()
        self.telegram = TelegramService()
        self.tz = ZoneInfo("America/Recife")

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _fixture_date(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("date") or "").strip()

    def _fixture_time(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("time") or "").strip()

    def _fixture_id(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("id") or "").strip()

    def _fixture_label(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        home = fixture.get("home_team", "Casa")
        away = fixture.get("away_team", "Fora")
        return f"{home} x {away}"

    def _build_startup_alert_key(self, fixture_id: str) -> str:
        return f"{fixture_id}_startup_sync"

    def _parse_fixture_datetime(self, payload: Dict) -> Optional[datetime]:
        fixture_date = self._fixture_date(payload)
        fixture_time = self._fixture_time(payload)

        if not fixture_date:
            return None

        normalized_time = (fixture_time or "00:00:00").strip()
        normalized_time = normalized_time.replace("Z", "")

        if "+" in normalized_time:
            normalized_time = normalized_time.split("+", 1)[0]

        if normalized_time.count(":") == 1:
            normalized_time = f"{normalized_time}:00"

        raw_value = f"{fixture_date} {normalized_time}"

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(raw_value, fmt).replace(tzinfo=self.tz)
            except ValueError:
                continue

        return None

    def _minutes_to_kickoff(self, payload: Dict) -> Optional[int]:
        fixture_dt = self._parse_fixture_datetime(payload)
        if not fixture_dt:
            return None

        delta = fixture_dt - self._now()
        return int(delta.total_seconds() // 60)

    def _should_send_startup_alert(self, payload: Dict) -> bool:
        minutes_to_kickoff = self._minutes_to_kickoff(payload)

        if minutes_to_kickoff is None:
            print(
                f"[POST_DEPLOY_SYNC] Sem horário válido para avaliar alerta startup | "
                f"fixture_id={self._fixture_id(payload)} | jogo={self._fixture_label(payload)}"
            )
            return False

        should_send = (
            self.STARTUP_ALERT_WINDOW_MIN
            <= minutes_to_kickoff
            <= self.STARTUP_ALERT_WINDOW_MAX
        )

        print(
            f"[POST_DEPLOY_SYNC] Janela startup | "
            f"fixture_id={self._fixture_id(payload)} | "
            f"jogo={self._fixture_label(payload)} | "
            f"minutes_to_kickoff={minutes_to_kickoff} | "
            f"send={should_send}"
        )
        return should_send

    def _deduplicate_payloads(self, payloads: List[Dict]) -> List[Dict]:
        unique: List[Dict] = []
        seen_ids: Set[str] = set()

        for payload in payloads:
            fixture_id = self._fixture_id(payload)
            if not fixture_id:
                print(
                    f"[POST_DEPLOY_SYNC] Jogo ignorado sem fixture_id: "
                    f"{self._fixture_label(payload)}"
                )
                continue

            if fixture_id in seen_ids:
                continue

            seen_ids.add(fixture_id)
            unique.append(payload)

        return unique

    def _filter_payloads_for_today(self, payloads: List[Dict]) -> List[Dict]:
        today = self._today()
        filtered: List[Dict] = []

        for payload in payloads:
            fixture_id = self._fixture_id(payload)
            fixture_date = self._fixture_date(payload)
            label = self._fixture_label(payload)

            if not fixture_date:
                print(
                    f"[POST_DEPLOY_SYNC] Ignorando sem data | "
                    f"fixture_id={fixture_id} | jogo={label}"
                )
                continue

            if fixture_date != today:
                print(
                    f"[POST_DEPLOY_SYNC] Ignorando fora do dia local | "
                    f"fixture_id={fixture_id} | jogo={label} | "
                    f"fixture_date={fixture_date} | today={today}"
                )
                continue

            filtered.append(payload)

        return filtered

    def _load_today_payloads(self) -> List[Dict]:
        today = self._today()

        day_payloads = self.daily_service.get_all_day_payloads(today)
        print(
            f"[POST_DEPLOY_SYNC] Jogos do dia inteiro encontrados: "
            f"{len(day_payloads)}"
        )

        all_payloads = self._deduplicate_payloads(day_payloads)
        all_payloads = self._filter_payloads_for_today(all_payloads)

        print(
            f"[POST_DEPLOY_SYNC] Total de jogos únicos válidos hoje: "
            f"{len(all_payloads)}"
        )
        return all_payloads

    def _persist_payloads(self, payloads: List[Dict]) -> int:
        processed = 0

        for payload in payloads:
            try:
                fixture_id = self._fixture_id(payload)
                label = self._fixture_label(payload)
                fixture_date = self._fixture_date(payload)

                print(
                    f"[POST_DEPLOY_SYNC] Persistindo | "
                    f"fixture_id={fixture_id} | jogo={label} | data={fixture_date}"
                )

                save_prediction(payload)
                processed += 1

            except Exception as e:
                fixture = payload.get("fixture") or {}
                print(
                    f"[POST_DEPLOY_SYNC] Erro ao persistir "
                    f"{fixture.get('home_team')} x {fixture.get('away_team')}: {e}"
                )

        print(
            f"[POST_DEPLOY_SYNC] Persistência concluída. "
            f"Jogos processados: {processed}"
        )
        return processed

    def _send_missing_alerts(self, payloads: List[Dict]) -> int:
        sent = 0

        for payload in payloads:
            fixture = payload.get("fixture") or {}
            fixture_id = str(fixture.get("id") or "").strip()
            home_team = fixture.get("home_team", "Casa")
            away_team = fixture.get("away_team", "Fora")

            if not fixture_id:
                continue

            if not self._should_send_startup_alert(payload):
                print(
                    f"[POST_DEPLOY_SYNC] Fora da janela de envio startup | "
                    f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                )
                continue

            startup_alert_key = self._build_startup_alert_key(fixture_id)

            if _already_sent_alert(startup_alert_key):
                print(
                    f"[POST_DEPLOY_SYNC] Alerta startup já existia, não reenviado | "
                    f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                )
                continue

            try:
                message = format_prediction_message(payload)
                result = self.telegram.send_message(message)

                if result.get("ok"):
                    _save_sent_alert(startup_alert_key)
                    sent += 1
                    print(
                        f"[POST_DEPLOY_SYNC] Alerta startup enviado com sucesso | "
                        f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                    )
                else:
                    print(
                        f"[POST_DEPLOY_SYNC] Falha ao enviar alerta startup | "
                        f"fixture_id={fixture_id} | retorno={result}"
                    )

            except Exception as e:
                print(
                    f"[POST_DEPLOY_SYNC] Erro ao enviar alerta startup | "
                    f"fixture_id={fixture_id} | erro={e}"
                )

        print(f"[POST_DEPLOY_SYNC] Alertas startup enviados: {sent}")
        return sent

    def _run_result_check(self) -> List[Dict]:
        pending = get_pending_predictions()
        print(f"[POST_DEPLOY_SYNC] Pendentes antes da checagem: {len(pending)}")

        updates = self.result_checker.check_pending_predictions()
        print(f"[POST_DEPLOY_SYNC] Jogos finalizados encontrados: {len(updates)}")

        if not updates:
            print("[POST_DEPLOY_SYNC] Nenhum resultado novo encontrado.")
        else:
            for item in updates:
                print(
                    f"[POST_DEPLOY_SYNC] Resultado atualizado | "
                    f"{item.get('home_team')} x {item.get('away_team')} | "
                    f"placar={item.get('home_score')}x{item.get('away_score')} | "
                    f"resultado={item.get('real_result')} | "
                    f"status={item.get('status')}"
                )

        return updates

    def run_once(self) -> Dict:
        print("[POST_DEPLOY_SYNC] Iniciando sincronização pós-deploy...")

        payloads = self._load_today_payloads()
        processed = self._persist_payloads(payloads)
        sent_alerts = self._send_missing_alerts(payloads)
        updates = self._run_result_check()

        print("[POST_DEPLOY_SYNC] Sincronização pós-deploy finalizada com sucesso.")

        return {
            "success": True,
            "processed": processed,
            "sent_alerts": sent_alerts,
            "updated_results": len(updates),
        }

    def run(self) -> Dict:
        return self.run_once()