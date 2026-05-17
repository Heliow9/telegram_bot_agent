from datetime import datetime, timedelta
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
from app.services.time_utils import event_payload_to_local_datetime
from app.services.scheduler_service import (
    _already_sent_alert,
    _save_sent_alert,
    build_alert_key,
)


class PostDeploySyncService:
    # No startup/deploy o bot deve persistir os jogos do dia, mas NÃO pode disparar análises pré-jogo futuras.
    # O alerta individual só é permitido na regra T-30: entre 29 e 31 minutos antes do kickoff.
    # No restart/deploy, se o bot voltar dentro da janela pré-live, ele ainda deve
    # conseguir enviar. Janela estreita 29-31 min perdia jogos por atraso de API.
    STARTUP_ALERT_WINDOW_MIN = 0
    STARTUP_ALERT_WINDOW_MAX = 30

    def __init__(self):
        self.daily_service = DailyLeaguesService()
        self.result_checker = ResultCheckerService()
        self.telegram = TelegramService()
        self.tz = ZoneInfo("America/Recife")

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _tomorrow(self) -> str:
        return (self._now() + timedelta(days=1)).strftime("%Y-%m-%d")

    def _fixture_date(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("local_date") or fixture.get("date") or "").strip()

    def _fixture_time(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("local_time") or fixture.get("time") or "").strip()

    def _fixture_id(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("id") or "").strip()

    def _fixture_label(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        home = fixture.get("home_team", "Casa")
        away = fixture.get("away_team", "Fora")
        return f"{home} x {away}"

    def _build_startup_alert_key(self, fixture_id: str, fixture_date: str | None = None) -> str:
        fixture_date = fixture_date or self._today()
        return f"{fixture_date}_{fixture_id}_startup_sync"

    def _parse_fixture_datetime(self, payload: Dict) -> Optional[datetime]:
        fixture_date = self._fixture_date(payload)
        fixture_time = self._fixture_time(payload)

        if not fixture_date:
            return None

        normalized_time = (fixture_time or "00:00:00").strip()
        normalized_time = normalized_time.replace("Z", "")

        if "T" in normalized_time:
            normalized_time = normalized_time.split("T", 1)[-1]

        if "+" in normalized_time:
            normalized_time = normalized_time.split("+", 1)[0]

        if normalized_time.count(":") == 1:
            normalized_time = f"{normalized_time}:00"

        if not normalized_time:
            normalized_time = "00:00:00"

        raw_value = f"{fixture_date} {normalized_time}"

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(raw_value, fmt).replace(tzinfo=self.tz)
            except ValueError:
                continue

        print(
            f"[POST_DEPLOY_SYNC] Falha ao parsear datetime | "
            f"fixture_id={self._fixture_id(payload)} | "
            f"raw_date={fixture_date} | raw_time={fixture_time} | "
            f"normalized_time={normalized_time}"
        )
        return None

    def _minutes_to_kickoff(self, payload: Dict) -> Optional[int]:
        fixture_dt = self._parse_fixture_datetime(payload)
        if not fixture_dt:
            return None

        delta = fixture_dt - self._now()
        return int(delta.total_seconds() // 60)

    def _should_send_startup_alert(self, payload: Dict) -> bool:
        """Permite alerta no startup somente se o jogo estiver exatamente na janela T-30."""
        minutes_to_kickoff = self._minutes_to_kickoff(payload)
        eligible = (
            minutes_to_kickoff is not None
            and self.STARTUP_ALERT_WINDOW_MIN <= minutes_to_kickoff <= self.STARTUP_ALERT_WINDOW_MAX
        )
        print(
            f"[POST_DEPLOY_SYNC] Checando alerta startup T-30 | "
            f"fixture_id={self._fixture_id(payload)} | "
            f"jogo={self._fixture_label(payload)} | "
            f"minutes_to_kickoff={minutes_to_kickoff} | eligible={eligible}"
        )
        return eligible

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

    def _filter_payloads_for_dates(self, payloads: List[Dict], allowed_dates: Set[str]) -> List[Dict]:
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

            if fixture_date not in allowed_dates:
                print(
                    f"[POST_DEPLOY_SYNC] Ignorando fora das datas alvo | "
                    f"fixture_id={fixture_id} | jogo={label} | "
                    f"fixture_date={fixture_date} | allowed={sorted(allowed_dates)}"
                )
                continue

            filtered.append(payload)

        return filtered

    def _load_payloads_for_dates(self, target_dates: List[str]) -> List[Dict]:
        aggregated: List[Dict] = []

        for target_date in target_dates:
            day_payloads = self.daily_service.get_all_day_payloads(target_date)
            print(
                f"[POST_DEPLOY_SYNC] Jogos encontrados para {target_date}: "
                f"{len(day_payloads)}"
            )
            aggregated.extend(day_payloads)

        all_payloads = self._deduplicate_payloads(aggregated)
        all_payloads = self._filter_payloads_for_dates(all_payloads, set(target_dates))

        print(
            f"[POST_DEPLOY_SYNC] Total de jogos únicos válidos nas datas {target_dates}: "
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

            fixture_date = self._fixture_date(payload) or self._today()
            startup_alert_key = self._build_startup_alert_key(fixture_id, fixture_date)
            regular_alert_key = build_alert_key(fixture_id)

            if _already_sent_alert(startup_alert_key) or _already_sent_alert(regular_alert_key):
                print(
                    f"[POST_DEPLOY_SYNC] Alerta já enviado, não reenviado | "
                    f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                )
                continue

            try:
                message = format_prediction_message(payload)
                result = self.telegram.send_message(message)

                if result.get("ok"):
                    _save_sent_alert(startup_alert_key)
                    _save_sent_alert(regular_alert_key)
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

        today = self._today()
        tomorrow = self._tomorrow()
        payloads = self._load_payloads_for_dates([today, tomorrow])
        processed = self._persist_payloads(payloads)
        today_payloads = [payload for payload in payloads if self._fixture_date(payload) == today]
        sent_alerts = self._send_missing_alerts(today_payloads)
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
