from pathlib import Path
import json

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.prediction_store import save_prediction
from app.services.result_checker_service import ResultCheckerService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import (
    format_result_message,
    pick_winner_photo_url,
)
from app.services.gemini_summary_service import GeminiSummaryService
from app.services.time_utils import now_local


SYNC_STATE_PATH = Path("data/post_deploy_sync_state.json")
POST_DEPLOY_RESULTS_SENT_PATH = Path("data/post_deploy_results_sent.json")


class PostDeploySyncService:
    def __init__(self):
        self.daily_service = DailyLeaguesService()
        self.result_checker = ResultCheckerService()
        self.telegram = TelegramService()
        self.gemini_summary = GeminiSummaryService()

    def _ensure_state_file(self):
        SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not SYNC_STATE_PATH.exists():
            SYNC_STATE_PATH.write_text(
                json.dumps({"last_run_date": None}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _ensure_results_sent_file(self):
        POST_DEPLOY_RESULTS_SENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not POST_DEPLOY_RESULTS_SENT_PATH.exists():
            POST_DEPLOY_RESULTS_SENT_PATH.write_text("[]", encoding="utf-8")

    def _load_state(self) -> dict:
        self._ensure_state_file()
        try:
            return json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"last_run_date": None}

    def _save_state(self, state: dict):
        self._ensure_state_file()
        SYNC_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_sent_results(self) -> list[str]:
        self._ensure_results_sent_file()
        try:
            data = json.loads(POST_DEPLOY_RESULTS_SENT_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def _save_sent_results(self, data: list[str]):
        self._ensure_results_sent_file()
        POST_DEPLOY_RESULTS_SENT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _already_sent_result(self, result_key: str) -> bool:
        return result_key in self._load_sent_results()

    def _mark_result_sent(self, result_key: str):
        data = self._load_sent_results()
        if result_key not in data:
            data.append(result_key)
            self._save_sent_results(data)

    def should_run_today(self) -> bool:
        today_str = now_local().strftime("%Y-%m-%d")
        state = self._load_state()
        return state.get("last_run_date") != today_str

    def mark_ran_today(self):
        today_str = now_local().strftime("%Y-%m-%d")
        self._save_state({"last_run_date": today_str})

    def _collect_today_payloads(self) -> list[dict]:
        all_payloads = []

        try:
            morning_payloads = self.daily_service.get_morning_payloads()
            print(
                f"[POST_DEPLOY_SYNC] Jogos da manhã encontrados: "
                f"{len(morning_payloads)}"
            )
            all_payloads.extend(morning_payloads)
        except Exception as e:
            print(f"[POST_DEPLOY_SYNC] Erro ao buscar jogos da manhã: {e}")

        try:
            afternoon_payloads = self.daily_service.get_afternoon_payloads()
            print(
                f"[POST_DEPLOY_SYNC] Jogos da tarde/noite encontrados: "
                f"{len(afternoon_payloads)}"
            )
            all_payloads.extend(afternoon_payloads)
        except Exception as e:
            print(f"[POST_DEPLOY_SYNC] Erro ao buscar jogos da tarde/noite: {e}")

        unique_payloads = {}
        for payload in all_payloads:
            fixture = payload.get("fixture", {})
            fixture_id = str(fixture.get("id", "")).strip()
            if fixture_id:
                unique_payloads[fixture_id] = payload

        return list(unique_payloads.values())

    def _persist_payloads(self, payloads: list[dict]) -> int:
        persisted = 0

        for payload in payloads:
            try:
                save_prediction(payload)
                persisted += 1
            except Exception as e:
                fixture = payload.get("fixture", {})
                print(
                    "[POST_DEPLOY_SYNC] Erro ao salvar "
                    f"fixture={fixture.get('id')} | "
                    f"{fixture.get('home_team')} x {fixture.get('away_team')}: {e}"
                )

        return persisted

    def _send_result_to_telegram(self, item: dict):
        fixture_id = str(item.get("fixture_id", ""))
        result_key = f"{fixture_id}_post_deploy_result"

        if not fixture_id:
            return

        if self._already_sent_result(result_key):
            print(
                f"[POST_DEPLOY_SYNC] Resultado já enviado anteriormente no pós-deploy: "
                f"{fixture_id}"
            )
            return

        try:
            ai_summary = self.gemini_summary.build_result_summary(item)
            caption = format_result_message(item, ai_summary=ai_summary)
            photo_url = pick_winner_photo_url(item)

            if photo_url:
                result = self.telegram.send_photo(photo_url, caption=caption)
            else:
                result = self.telegram.send_message(caption)

            print(f"[POST_DEPLOY_SYNC] Retorno Telegram: {result}")

            if result.get("ok"):
                self._mark_result_sent(result_key)
                print(
                    "[POST_DEPLOY_SYNC] Resultado enviado com sucesso: "
                    f"{item.get('home_team')} x {item.get('away_team')} | "
                    f"{item.get('status')}"
                )
            else:
                print(f"[POST_DEPLOY_SYNC] Falha ao enviar resultado: {result}")

        except Exception as e:
            print(f"[POST_DEPLOY_SYNC] Erro ao enviar resultado no Telegram: {e}")

    def run_once(self):
        if not self.should_run_today():
            print("[POST_DEPLOY_SYNC] Já executado hoje. Ignorando nova execução.")
            return

        print("[POST_DEPLOY_SYNC] Iniciando sincronização pós-deploy...")

        payloads = self._collect_today_payloads()
        print(
            f"[POST_DEPLOY_SYNC] Total de jogos únicos encontrados hoje: "
            f"{len(payloads)}"
        )

        persisted = self._persist_payloads(payloads)
        print(
            f"[POST_DEPLOY_SYNC] Persistência concluída. "
            f"Jogos processados: {persisted}"
        )

        try:
            updates = self.result_checker.check_pending_predictions()
            print(f"[POST_DEPLOY_SYNC] Jogos finalizados encontrados: {len(updates)}")

            if updates:
                for item in updates:
                    print(
                        "[POST_DEPLOY_SYNC] Resolvido: "
                        f"{item.get('home_team')} x {item.get('away_team')} | "
                        f"Placar: {item.get('home_score')} x {item.get('away_score')} | "
                        f"Status: {item.get('status')}"
                    )
                    self._send_result_to_telegram(item)
            else:
                print("[POST_DEPLOY_SYNC] Nenhum resultado novo encontrado.")

        except Exception as e:
            print(f"[POST_DEPLOY_SYNC] Erro ao checar resultados: {e}")

        self.mark_ran_today()
        print("[POST_DEPLOY_SYNC] Sincronização pós-deploy finalizada com sucesso.")