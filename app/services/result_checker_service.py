from datetime import timedelta
from typing import Dict, List, Optional

from app.services.sportsdb_api import SportsDBAPI
from app.services.prediction_store import (
    get_pending_predictions,
    update_prediction_result,
    build_stats,
)
from app.services.time_utils import parse_event_utc, now_utc


class ResultCheckerService:
    FINISHED_STATUSES = {
        "match finished",
        "finished",
        "ft",
        "after extra time",
        "aet",
        "full time",
        "penalties",
        "pen",
        "after penalties",
    }

    NOT_STARTED_STATUSES = {
        "not started",
        "ns",
        "scheduled",
    }

    LIVE_STATUSES = {
        "1h",
        "2h",
        "ht",
        "half time",
        "live",
        "in play",
        "break",
        "et",
    }

    FALLBACK_FINISH_AFTER_MINUTES = 120

    def __init__(self):
        self.api = SportsDBAPI()

    def _normalize_fixture_id(self, fixture_id) -> str:
        if fixture_id is None:
            return ""
        return str(fixture_id).strip()

    def _safe_int(self, value) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_result_code(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        value = str(value).strip().lower()

        mapping = {
            "1": "1",
            "home": "1",
            "h": "1",
            "2": "2",
            "away": "2",
            "a": "2",
            "x": "X",
            "draw": "X",
            "d": "X",
            "empate": "X",
        }

        return mapping.get(value, value.upper())

    def _normalize_locked(self, value: Optional[str]) -> str:
        return str(value or "").strip().lower()

    def _normalize_status_text(self, value: Optional[str]) -> str:
        return str(value or "").strip()

    def _result_from_scores(self, home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return "1"
        if away_score > home_score:
            return "2"
        return "X"

    def _is_match_time_expired(self, details: Dict) -> bool:
        date_event = str(details.get("dateEvent") or details.get("date_event") or "").strip()
        time_event = str(details.get("strTime") or details.get("time_event") or "").strip()

        event_dt_utc = parse_event_utc(date_event, time_event)
        if event_dt_utc is None:
            return False

        deadline = event_dt_utc + timedelta(minutes=self.FALLBACK_FINISH_AFTER_MINUTES)
        expired = now_utc() >= deadline

        if expired:
            print(
                "[RESULT CHECKER] Fallback temporal ativado | "
                f"date_event={date_event} | time_event={time_event} | "
                f"deadline_utc={deadline.isoformat()} | now_utc={now_utc().isoformat()}"
            )

        return expired

    def _is_finished_from_details(self, details: Dict) -> bool:
        locked = self._normalize_locked(details.get("strLocked"))
        if locked == "locked":
            return True

        candidates = [
            details.get("strStatus"),
            details.get("strProgress"),
            details.get("status"),
            details.get("status_text"),
        ]

        normalized_status = ""
        for raw in candidates:
            if not raw:
                continue

            normalized = str(raw).strip().lower()
            if normalized:
                normalized_status = normalized

            if normalized in self.FINISHED_STATUSES:
                return True

            if "finished" in normalized:
                return True

        home_score = self._safe_int(
            details.get("intHomeScore", details.get("home_score"))
        )
        away_score = self._safe_int(
            details.get("intAwayScore", details.get("away_score"))
        )

        has_score = home_score is not None and away_score is not None

        if has_score and self._is_match_time_expired(details):
            print(
                "[RESULT CHECKER] Finalizado por fallback temporal com placar | "
                f"status={normalized_status or '-'} | locked={locked or '-'} | "
                f"score={home_score}x{away_score}"
            )
            return True

        if has_score and normalized_status:
            if normalized_status in self.NOT_STARTED_STATUSES:
                return False

            if normalized_status in self.LIVE_STATUSES:
                return False

        return False

    def _extract_result_from_details(self, details: Dict) -> Optional[Dict]:
        if not details:
            return None

        home_score = self._safe_int(
            details.get("intHomeScore", details.get("home_score"))
        )
        away_score = self._safe_int(
            details.get("intAwayScore", details.get("away_score"))
        )

        finished = self._is_finished_from_details(details)

        status_text = (
            details.get("strStatus")
            or details.get("strProgress")
            or details.get("status_text")
            or details.get("status")
        )

        result = None
        if finished:
            result = (
                self._normalize_result_code(details.get("result"))
                or self._result_from_scores(home_score, away_score)
            )

        return {
            "fixture_id": str(details.get("idEvent") or details.get("fixture_id") or ""),
            "finished": finished,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "status_text": self._normalize_status_text(status_text),
            "locked": self._normalize_locked(details.get("strLocked")),
            "date_event": str(details.get("dateEvent") or details.get("date_event") or "").strip(),
            "time_event": str(details.get("strTime") or details.get("time_event") or "").strip(),
        }

    def _merge_result_sources(
        self,
        fixture_id: str,
        result_data: Optional[Dict],
        event_details: Optional[Dict],
    ) -> Optional[Dict]:
        result_data = result_data or {}
        event_details = event_details or {}

        detail_result = self._extract_result_from_details(event_details)

        raw_result = self._normalize_result_code(result_data.get("result"))
        raw_home_score = self._safe_int(result_data.get("home_score"))
        raw_away_score = self._safe_int(result_data.get("away_score"))
        raw_finished = bool(result_data.get("finished"))
        raw_status = self._normalize_status_text(result_data.get("status_text"))

        merged_home_score = (
            raw_home_score
            if raw_home_score is not None
            else (detail_result or {}).get("home_score")
        )
        merged_away_score = (
            raw_away_score
            if raw_away_score is not None
            else (detail_result or {}).get("away_score")
        )

        merged_finished = raw_finished or bool((detail_result or {}).get("finished"))
        merged_status = raw_status or (detail_result or {}).get("status_text")
        merged_locked = result_data.get("locked") or (detail_result or {}).get("locked")
        merged_date_event = result_data.get("date_event") or (detail_result or {}).get("date_event")
        merged_time_event = result_data.get("time_event") or (detail_result or {}).get("time_event")

        merged_result = None
        if merged_finished:
            merged_result = (
                raw_result
                or (detail_result or {}).get("result")
                or self._result_from_scores(merged_home_score, merged_away_score)
            )

        is_live = False
        normalized_status = str(merged_status or "").strip().lower()

        if normalized_status in self.LIVE_STATUSES:
            is_live = True

        if normalized_status in self.NOT_STARTED_STATUSES:
            is_live = False

        if merged_finished:
            is_live = False

        return {
            "fixture_id": fixture_id,
            "finished": merged_finished,
            "home_score": merged_home_score,
            "away_score": merged_away_score,
            "result": merged_result,
            "status_text": merged_status,
            "locked": merged_locked,
            "is_live": is_live,
            "date_event": merged_date_event,
            "time_event": merged_time_event,
        }

    def check_pending_predictions(self) -> List[Dict]:
        pending = get_pending_predictions()
        updates = []

        print(f"[RESULT CHECKER] Pendentes: {len(pending)}")

        for item in pending:
            fixture_id = self._normalize_fixture_id(item.get("fixture_id"))
            if not fixture_id:
                print("[RESULT CHECKER] Item ignorado: fixture_id vazio")
                continue

            print(
                f"[RESULT CHECKER] Checando fixture={fixture_id} | "
                f"{item.get('home_team')} x {item.get('away_team')}"
            )

            result_data = {}
            event_details = {}

            try:
                result_data = self.api.get_event_result(fixture_id) or {}
            except Exception as e:
                print(f"[RESULT CHECKER] Erro em get_event_result({fixture_id}): {e}")

            try:
                event_details = self.api.get_event_details(fixture_id) or {}
            except Exception as e:
                print(f"[RESULT CHECKER] Erro em get_event_details({fixture_id}): {e}")

            merged = self._merge_result_sources(
                fixture_id=fixture_id,
                result_data=result_data,
                event_details=event_details,
            )

            print(f"[RESULT CHECKER] Resultado consolidado: {merged}")

            if not merged:
                continue

            if not merged.get("finished"):
                print(
                    f"[RESULT CHECKER] Ainda não finalizado: {fixture_id} | "
                    f"status={merged.get('status_text')} | locked={merged.get('locked')}"
                )
                continue

            if merged.get("home_score") is None or merged.get("away_score") is None:
                print(
                    f"[RESULT CHECKER] Finalizado sem placar consistente: {fixture_id} | "
                    f"dados={merged}"
                )
                continue

            if not merged.get("result"):
                print(
                    f"[RESULT CHECKER] Finalizado sem resultado definido: {fixture_id} | "
                    f"dados={merged}"
                )
                continue

            update_prediction_result(
                fixture_id=fixture_id,
                result=merged["result"],
                home_score=merged["home_score"],
                away_score=merged["away_score"],
                status_text=merged.get("status_text"),
                result_source="sportsdb",
                is_live=merged.get("is_live", False),
                finished=merged.get("finished", False),
            )

            updates.append({
                "fixture_id": fixture_id,
                "league": item.get("league"),
                "home_team": item.get("home_team"),
                "away_team": item.get("away_team"),
                "pick": item.get("pick"),
                "confidence": item.get("confidence"),
                "real_result": merged["result"],
                "home_score": merged["home_score"],
                "away_score": merged["away_score"],
                "status": "hit" if str(item.get("pick")) == str(merged["result"]) else "miss",
                "home_badge": event_details.get("strHomeTeamBadge") if event_details else None,
                "away_badge": event_details.get("strAwayTeamBadge") if event_details else None,
            })

            print(
                f"[RESULT CHECKER] Atualizado fixture={fixture_id} | "
                f"placar={merged['home_score']}x{merged['away_score']} | "
                f"resultado={merged['result']}"
            )

        return updates

    def get_stats(self) -> Dict:
        return build_stats()