from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.daily_leagues_service import DailyLeaguesService
from app.constants import BASKETBALL_LEAGUES


if __name__ == "__main__":
    service = DailyLeaguesService()
    today = datetime.now(ZoneInfo("America/Recife")).strftime("%Y-%m-%d")
    print("Ligas de basquete configuradas:")
    for league in BASKETBALL_LEAGUES:
        print(f"- {league['display_name']} | id={league['id']} | name={league['name']}")

    payloads = service.get_basketball_all_day_payloads(today)
    print(f"\nPayloads de basquete hoje ({today}): {len(payloads)}")
    for payload in payloads[:10]:
        fixture = payload.get("fixture", {})
        analysis = payload.get("analysis", {})
        print(
            f"{fixture.get('local_time')} | {payload.get('league', {}).get('display_name')} | "
            f"{fixture.get('home_team')} x {fixture.get('away_team')} | "
            f"vencedor={analysis.get('suggested_pick')} prob={analysis.get('best_probability'):.2%} | "
            f"total={analysis.get('total_points_label')} prob={analysis.get('total_points_probability'):.2%}"
        )

    upcoming = service.get_basketball_upcoming_payloads(hours=72)
    print(f"\nPróximos 72h: {len(upcoming)}")
