from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()

events = api.get_next_events_by_league_list("4351")

print(f"Total: {len(events)}")
for event in events[:10]:
    print(
        f"{event.get('strHomeTeam')} x {event.get('strAwayTeam')} | "
        f"{event.get('dateEvent')} {event.get('strTime')} | "
        f"id={event.get('idEvent')}"
    )