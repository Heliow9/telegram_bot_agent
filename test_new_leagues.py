from datetime import datetime
from app.constants import LEAGUES
from app.services.sportsdb_api import SportsDBAPI
from app.services.time_utils import format_local_datetime


api = SportsDBAPI()
today = datetime.now().strftime("%Y-%m-%d")

target_keys = {"ucl", "sud", "lib", "champ"}


def main():
    print(f"Testando novas ligas para a data: {today}\n")

    selected_leagues = [league for league in LEAGUES if league["key"] in target_keys]

    if not selected_leagues:
        print("Nenhuma das ligas alvo foi encontrada em LEAGUES.")
        return

    total_all = 0

    for league in selected_leagues:
        league_name = league["name"]
        display_name = league["display_name"]

        print("=" * 70)
        print(f"{display_name}")
        print(f"name usado na API: {league_name}")
        print(f"id: {league['id']} | season: {league['season']} | priority: {league['priority']}")
        print("-" * 70)

        try:
            events = api.get_events_by_day_list(today, league_name)
        except Exception as e:
            print(f"Erro ao buscar jogos: {e}\n")
            continue

        count = len(events)
        total_all += count
        print(f"Total de jogos encontrados hoje: {count}")

        if not events:
            print("Nenhum jogo encontrado para hoje.\n")
            continue

        for idx, event in enumerate(events, start=1):
            home_team = event.get("strHomeTeam", "Casa")
            away_team = event.get("strAwayTeam", "Fora")
            date_event = event.get("dateEvent", "")
            time_event = event.get("strTime", "")
            event_id = event.get("idEvent", "")
            status = event.get("strStatus", "N/A")

            local_date, local_time = format_local_datetime(date_event, time_event)
            local_time = local_time[:5] if local_time else "--:--"

            print(
                f"{idx}. {home_team} x {away_team} | "
                f"{local_date} {local_time} | "
                f"status={status} | "
                f"id={event_id}"
            )

        print()

    print("=" * 70)
    print(f"Total geral de jogos encontrados nas novas ligas: {total_all}")


if __name__ == "__main__":
    main()