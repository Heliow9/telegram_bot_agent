from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()

data = api.next_events_by_league_id("4351")
events = data.get("events", [])

print(f"Total de jogos do Brasileirão encontrados: {len(events)}")

for event in events[:10]:
    print(
        f"{event.get('strHomeTeam')} x {event.get('strAwayTeam')} | "
        f"{event.get('dateEvent')} {event.get('strTime')} | "
        f"id={event.get('idEvent')}"
    )