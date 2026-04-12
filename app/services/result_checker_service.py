from typing import Dict, List
from app.services.sportsdb_api import SportsDBAPI
from app.services.prediction_store import (
    get_pending_predictions,
    update_prediction_result,
    build_stats,
)


class ResultCheckerService:
    def __init__(self):
        self.api = SportsDBAPI()

    def check_pending_predictions(self) -> List[Dict]:
        pending = get_pending_predictions()
        updates = []

        print(f"[RESULT CHECKER] Pendentes: {len(pending)}")

        for item in pending:
            fixture_id = str(item.get("fixture_id"))
            if not fixture_id:
                continue

            print(
                f"[RESULT CHECKER] Checando fixture={fixture_id} | "
                f"{item.get('home_team')} x {item.get('away_team')}"
            )

            result_data = self.api.get_event_result(fixture_id)
            print(f"[RESULT CHECKER] Retorno API: {result_data}")

            if not result_data:
                continue

            if not result_data.get("finished"):
                print(f"[RESULT CHECKER] Ainda não finalizado: {fixture_id}")
                continue

            update_prediction_result(
                fixture_id=fixture_id,
                result=result_data["result"],
                home_score=result_data["home_score"],
                away_score=result_data["away_score"],
            )

            updates.append({
                "fixture_id": fixture_id,
                "home_team": item.get("home_team"),
                "away_team": item.get("away_team"),
                "pick": item.get("pick"),
                "real_result": result_data["result"],
                "home_score": result_data["home_score"],
                "away_score": result_data["away_score"],
                "status": "hit" if item.get("pick") == result_data["result"] else "miss",
            })

        return updates

    def get_stats(self) -> Dict:
        return build_stats()