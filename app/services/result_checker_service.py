from typing import Dict, List, Optional

from app.services.sportsdb_api import SportsDBAPI
from app.services.prediction_store import (
    get_pending_predictions,
    update_prediction_result,
    build_stats,
)


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
    }

    NOT_STARTED_STATUSES = {
        "not started",
        "ns",
        "scheduled",
    }

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

    def _result_from_scores(
        self,
        home_score: Optional[int],
        away_score: Optional[int],
    ) -> Optional[str]:
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return "1"
        if away_score > home_score:
            return "2"
        return "X"

    def _is_finished_from_details(self, details: Dict) -> bool:
        candidates = [
            details.get("strStatus"),
            details.get("strProgress"),
            details.get("status"),
            details.get("status_text"),
        ]

        for raw in candidates:
            if not raw:
                continue

            normalized = str(raw).strip().lower()

            if normalized in self.FINISHED_STATUSES:
                return True

            if "finished" in normalized:
                return True

            if normalized in {"ft", "aet", "pen"}:
                return True

        home_score = self._safe_int(
            details.get("intHomeScore", details.get("home_score"))
        )
        away_score = self._safe_int(
            details.get("intAwayScore", details.get("away_score"))
        )

        if home_score is not None and away_score is not None:
            status = str(
                details.get("strStatus")
                or details.get("status")
                or details.get("status_text")
                or ""
            ).strip().lower()

            if status not in self.NOT_STARTED_STATUSES:
                return True

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

        result = (
            self._normalize_result_code(details.get("result"))
            or self._result_from_scores(home_score, away_score)
        )

        finished = self._is_finished_from_details(details)

        return {
            "fixture_id": str(details.get("idEvent") or details.get("fixture_id") or ""),
            "finished": finished,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "status_text": (
                details.get("strStatus")
                or details.get("strProgress")
                or details.get("status_text")
                or details.get("status")
            ),
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
        raw_status = result_data.get("status_text")

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

        merged_result = (
            raw_result
            or (detail_result or {}).get("result")
            or self._result_from_scores(merged_home_score, merged_away_score)
        )

        merged_finished = raw_finished or bool((detail_result or {}).get("finished"))
        merged_status = raw_status or (detail_result or {}).get("status_text")

        return {
            "fixture_id": fixture_id,
            "finished": merged_finished,
            "home_score": merged_home_score,
            "away_score": merged_away_score,
            "result": merged_result,
            "status_text": merged_status,
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
                    f"status={merged.get('status_text')}"
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