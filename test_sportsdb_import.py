from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()
print("Import ok")
print(api.all_leagues())