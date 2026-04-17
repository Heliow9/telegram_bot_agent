from datetime import timedelta
from typing import Dict, List, Optional

from app.constants import LEAGUES
from app.config import settings
from app.services.gemini_summary_service import GeminiSummaryService
from app.services.live_signal_service import LiveSignalService
from app.services.live_state_service import LiveStateService
from app.services.runtime_config_service import load_runtime_config
from app.services.sportsdb_api import SportsDBAPI
from app.services.telegram_service import TelegramService
from app.services.time_utils import now_local
from app.services.prediction_store import (
    get_prediction_by_fixture_id,
    update_prediction_live_state,
)


class LiveMatchMonitorService:
    def __init__(self):
        self.api = SportsDBAPI()
        self.telegram = TelegramService()
        self.gemini = GeminiSummaryService()
        self.state_service = LiveStateService()
        self.signal_service = LiveSignalService()

    def _runtime(self) -> Dict:
        return load_runtime_config()

    def _checkpoints(self) -> List[int]:
        runtime = self._runtime()
        raw = runtime.get(
            "live_minute_checkpoints",
            settings.live_minute_checkpoints,
        )

        if isinstance(raw, list):
            values = raw
        else:
            values = str(raw).split(",")

        checkpoints = []
        for item in values:
            try:
                value = int(str(item).strip())
                if value > 0:
                    checkpoints.append(value)
            except Exception:
                continue

        if not checkpoints:
            return [15, 30, 45, 60, 75]

        return sorted(set(checkpoints))

    def _today_candidates(self) -> List[str]:
        today = now_local().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        return [
            yesterday.strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d"),
            tomorrow.strftime("%Y-%m-%d"),
        ]

    def _is_live_status(self, status_text: str) -> bool:
        status = (status_text or "").strip().upper()
        if not status:
            return False

        finished_statuses = {
            "FT",
            "AET",
            "PEN",
            "FULL TIME",
            "MATCH FINISHED",
            "AFTER EXTRA TIME",
            "AFTER PENALTIES",
            "FINISHED",
            "POSTPONED",
            "CANCELLED",
            "NS",
        }

        if status in finished_statuses:
            return False

        return True

    def _extract_elapsed(self, event: Dict) -> Optional[int]:
        candidates = [
            event.get("intTime"),
            event.get("strProgress"),
            event.get("intElapsed"),
        ]

        for value in candidates:
            if value is None:
                continue
            try:
                raw = str(value).strip().replace("'", "")
                if raw.isdigit():
                    return int(raw)
            except Exception:
                continue

        return None

    def _match_clock(self, event: Dict) -> str:
        elapsed = self._extract_elapsed(event)
        if elapsed is not None:
            return f"{elapsed}'"

        status = (event.get("strStatus") or "").strip()
        return status if status else "Ao vivo"

    def _checkpoint_to_send(
        self,
        elapsed: Optional[int],
        already_sent: List[int],
    ) -> Optional[int]:
        if elapsed is None:
            return None

        for checkpoint in self._checkpoints():
            if elapsed >= checkpoint and checkpoint not in already_sent:
                return checkpoint
        return None

    def _build_snapshot(self, event: Dict, league_meta: Dict) -> Dict:
        home_score = event.get("intHomeScore")
        away_score = event.get("intAwayScore")

        try:
            home_score = int(home_score) if home_score is not None else 0
        except (TypeError, ValueError):
            home_score = 0

        try:
            away_score = int(away_score) if away_score is not None else 0
        except (TypeError, ValueError):
            away_score = 0

        elapsed = self._extract_elapsed(event)
        status_text = (event.get("strStatus") or "").strip()

        signal, signal_reason = self.signal_service.evaluate(
            {
                "home_score": home_score,
                "away_score": away_score,
                "status_text": status_text,
            }
        )

        return {
            "fixture_id": str(event.get("idEvent", "")),
            "league": league_meta["display_name"],
            "home_team": event.get("strHomeTeam", "Casa"),
            "away_team": event.get("strAwayTeam", "Fora"),
            "home_score": home_score,
            "away_score": away_score,
            "status_text": status_text,
            "elapsed": elapsed,
            "match_clock": self._match_clock(event),
            "score_signature": f"{home_score}-{away_score}",
            "goal_signature": f"{home_score}-{away_score}",
            "live_signal": signal,
            "signal_reason": signal_reason,
            "scoring_team": None,
            "sent_checkpoints": [],
        }

    def _guess_scoring_team(self, previous: Dict, current: Dict) -> Optional[str]:
        prev_home = int(previous.get("home_score", 0) or 0)
        prev_away = int(previous.get("away_score", 0) or 0)
        curr_home = int(current.get("home_score", 0) or 0)
        curr_away = int(current.get("away_score", 0) or 0)

        if curr_home > prev_home:
            return current.get("home_team")

        if curr_away > prev_away:
            return current.get("away_team")

        return None

    def _send_goal_alert(self, snapshot: Dict):
        ai_text = self.gemini.build_live_goal_summary(snapshot)

        if ai_text:
            text = (
                f"⚽ {snapshot['league']}\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x "
                f"{snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"{ai_text}"
            )
        else:
            scoring_team = snapshot.get("scoring_team") or "Um dos times"
            text = (
                f"⚽ {snapshot['league']}\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x "
                f"{snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"Gol de {scoring_team}. Tempo de jogo: "
                f"{snapshot.get('match_clock', 'Ao vivo')}."
            )

        result = self.telegram.send_message(text)
        print(f"[LIVE] Alerta de gol enviado: {result}")

    def _send_checkpoint_alert(self, snapshot: Dict, checkpoint: int):
        ai_text = self.gemini.build_live_checkpoint_summary(snapshot)

        signal_emoji = {
            "casa_favorável": "📈",
            "fora_favorável": "📉",
            "neutro": "⚖️",
        }.get(snapshot.get("live_signal"), "⚖️")

        if ai_text:
            text = (
                f"{signal_emoji} {snapshot['league']} | {checkpoint}'\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x "
                f"{snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"{ai_text}"
            )
        else:
            text = (
                f"{signal_emoji} {snapshot['league']} | {checkpoint}'\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x "
                f"{snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"{snapshot.get('signal_reason', 'Sem leitura forte no momento.')}"
            )

        result = self.telegram.send_message(text)
        print(f"[LIVE] Atualização {checkpoint}' enviada: {result}")

    def _collect_candidate_events(self) -> List[Dict]:
        all_events = []
        seen_ids = set()

        for league_meta in LEAGUES:
            for date_str in self._today_candidates():
                try:
                    events = self.api.get_events_by_day_list(
                        date_str,
                        league_meta["name"],
                    )
                    for event in events:
                        event_id = str(event.get("idEvent", ""))
                        if not event_id or event_id in seen_ids:
                            continue
                        seen_ids.add(event_id)
                        event["_league_meta"] = league_meta
                        all_events.append(event)
                except Exception as e:
                    print(
                        f"[LIVE] Erro buscando eventos "
                        f"{league_meta['display_name']} em {date_str}: {e}"
                    )

        return all_events

    def _should_skip_live_update(self, fixture_id: str) -> bool:
        existing = get_prediction_by_fixture_id(fixture_id)
        if not existing:
            return False

        status = str(existing.get("status") or "").strip().lower()
        return status in {"hit", "miss"}

    def _clear_not_live_if_needed(self, fixture_id: str, event: Dict):
        existing = get_prediction_by_fixture_id(fixture_id)
        if not existing:
            return

        status = str(existing.get("status") or "").strip().lower()
        if status in {"hit", "miss"}:
            return

        if bool(existing.get("is_live")):
            update_prediction_live_state(
                fixture_id=fixture_id,
                home_score=event.get("intHomeScore"),
                away_score=event.get("intAwayScore"),
                status_text=(event.get("strStatus") or "").strip() or "Não ao vivo",
                is_live=False,
            )
            print(f"[LIVE] Jogo removido do modo live | fixture_id={fixture_id}")

    def monitor_live_matches(self):
        candidate_events = self._collect_candidate_events()
        live_events = []

        for event in candidate_events:
            fixture_id = str(event.get("idEvent", "")).strip()
            status_text = (event.get("strStatus") or "").strip()

            if not fixture_id:
                continue

            if self._is_live_status(status_text):
                live_events.append(event)
            else:
                self._clear_not_live_if_needed(fixture_id, event)

        print(
            f"[LIVE] Jogos candidatos: {len(candidate_events)} | "
            f"ao vivo detectados: {len(live_events)}"
        )

        for event in live_events:
            try:
                fixture_id = str(event.get("idEvent", ""))
                if not fixture_id:
                    continue

                if self._should_skip_live_update(fixture_id):
                    print(
                        f"[LIVE] Ignorando atualização live de jogo já resolvido | "
                        f"fixture_id={fixture_id}"
                    )
                    continue

                league_meta = event.get("_league_meta")
                if not league_meta:
                    continue

                details = self.api.get_event_details(fixture_id) or event

                current_status = (details.get("strStatus") or event.get("strStatus") or "").strip()
                if not self._is_live_status(current_status):
                    self._clear_not_live_if_needed(fixture_id, details)
                    continue

                snapshot = self._build_snapshot(details, league_meta)

                previous = self.state_service.get_fixture_state(fixture_id) or {}
                sent_checkpoints = previous.get("sent_checkpoints", [])
                snapshot["sent_checkpoints"] = sent_checkpoints

                previous_score = previous.get("score_signature")
                current_score = snapshot.get("score_signature")

                if previous and previous_score != current_score:
                    snapshot["scoring_team"] = self._guess_scoring_team(
                        previous,
                        snapshot,
                    )
                    self._send_goal_alert(snapshot)

                checkpoint = self._checkpoint_to_send(
                    snapshot.get("elapsed"),
                    sent_checkpoints,
                )
                if checkpoint is not None:
                    self._send_checkpoint_alert(snapshot, checkpoint)
                    snapshot["sent_checkpoints"] = sorted(
                        set(sent_checkpoints + [checkpoint])
                    )

                update_prediction_live_state(
                    fixture_id=fixture_id,
                    home_score=snapshot.get("home_score"),
                    away_score=snapshot.get("away_score"),
                    status_text=snapshot.get("status_text") or snapshot.get("match_clock"),
                    is_live=True,
                )

                self.state_service.update_fixture_state(fixture_id, snapshot)

            except Exception as e:
                print(
                    f"[LIVE] Erro no monitoramento do evento "
                    f"{event.get('idEvent')}: {e}"
                )