from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Set

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.prediction_store import (
    save_prediction,
    get_pending_predictions,
)
from app.services.result_checker_service import ResultCheckerService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import format_prediction_message
from app.services.scheduler_service import (
    build_alert_key,
    _already_sent_alert,
    _save_sent_alert,
)


class PostDeploySyncService:
    def __init__(self):
        self.daily_service = DailyLeaguesService()
        self.result_checker = ResultCheckerService()
        self.telegram = TelegramService()
        self.tz = ZoneInfo("America/Recife")

    def _today(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    def _fixture_date(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("date") or "").strip()

    def _fixture_id(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        return str(fixture.get("id") or "").strip()

    def _fixture_label(self, payload: Dict) -> str:
        fixture = payload.get("fixture") or {}
        home = fixture.get("home_team", "Casa")
        away = fixture.get("away_team", "Fora")
        return f"{home} x {away}"

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

        morning_payloads = self.daily_service.get_morning_payloads(today)
        print(
            f"[POST_DEPLOY_SYNC] Jogos da manhã encontrados: "
            f"{len(morning_payloads)}"
        )

        afternoon_payloads = self.daily_service.get_afternoon_payloads(today)
        print(
            f"[POST_DEPLOY_SYNC] Jogos da tarde/noite encontrados: "
            f"{len(afternoon_payloads)}"
        )

        all_payloads = morning_payloads + afternoon_payloads
        all_payloads = self._deduplicate_payloads(all_payloads)
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

            alert_key = build_alert_key(fixture_id)

            if _already_sent_alert(alert_key):
                print(
                    f"[POST_DEPLOY_SYNC] Alerta já existia, não reenviado | "
                    f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                )
                continue

            try:
                message = format_prediction_message(payload)
                result = self.telegram.send_message(message)

                if result.get("ok"):
                    _save_sent_alert(alert_key)
                    sent += 1
                    print(
                        f"[POST_DEPLOY_SYNC] Alerta pendente enviado com sucesso | "
                        f"fixture_id={fixture_id} | jogo={home_team} x {away_team}"
                    )
                else:
                    print(
                        f"[POST_DEPLOY_SYNC] Falha ao enviar alerta pendente | "
                        f"fixture_id={fixture_id} | retorno={result}"
                    )

            except Exception as e:
                print(
                    f"[POST_DEPLOY_SYNC] Erro ao enviar alerta pendente | "
                    f"fixture_id={fixture_id} | erro={e}"
                )

        print(f"[POST_DEPLOY_SYNC] Alertas pendentes enviados no startup: {sent}")
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