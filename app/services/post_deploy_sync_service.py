from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Set

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.prediction_store import (
    save_prediction,
    get_pending_predictions,
)
from app.services.result_checker_service import ResultCheckerService


class PostDeploySyncService:
    def __init__(self):
        self.daily_service = DailyLeaguesService()
        self.result_checker = ResultCheckerService()
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

    def _is_payload_for_today(self, payload: Dict) -> bool:
        fixture_date = self._fixture_date(payload)
        today = self._today()
        return fixture_date == today

    def _deduplicate_payloads(self, payloads: List[Dict]) -> List[Dict]:
        unique: List[Dict] = []
        seen_ids: Set[str] = set()

        for payload in payloads:
            fixture_id = self._fixture_id(payload)
            if not fixture_id:
                print(f"[POST_DEPLOY_SYNC] Jogo ignorado sem fixture_id: {self._fixture_label(payload)}")
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
        morning_payloads = self.daily_service.get_morning_payloads()
        print(f"[POST_DEPLOY_SYNC] Jogos da manhã encontrados: {len(morning_payloads)}")

        afternoon_payloads = self.daily_service.get_afternoon_payloads()
        print(f"[POST_DEPLOY_SYNC] Jogos da tarde/noite encontrados: {len(afternoon_payloads)}")

        all_payloads = morning_payloads + afternoon_payloads
        all_payloads = self._deduplicate_payloads(all_payloads)
        all_payloads = self._filter_payloads_for_today(all_payloads)

        print(f"[POST_DEPLOY_SYNC] Total de jogos únicos válidos hoje: {len(all_payloads)}")
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

        print(f"[POST_DEPLOY_SYNC] Persistência concluída. Jogos processados: {processed}")
        return processed

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

    def run(self) -> Dict:
        print("[POST_DEPLOY_SYNC] Iniciando sincronização pós-deploy...")

        payloads = self._load_today_payloads()
        processed = self._persist_payloads(payloads)
        updates = self._run_result_check()

        print("[POST_DEPLOY_SYNC] Sincronização pós-deploy finalizada com sucesso.")

        return {
            "success": True,
            "processed": processed,
            "updated_results": len(updates),
        }