from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()
today = datetime.now().strftime("%Y-%m-%d")

events = api.get_events_by_day_list(today, "Brazilian Serie A")

print(f"Total no dia: {len(events)}")
for event in events:
    print(
        f"{event.get('strHomeTeam')} x {event.get('strAwayTeam')} | "
        f"{event.get('dateEvent')} {event.get('strTime')}"
    )