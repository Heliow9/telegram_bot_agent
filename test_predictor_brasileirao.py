from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()
today = datetime.now().strftime("%Y-%m-%d")

data = api.events_by_day(today, "Brazilian Serie A")
print(data)