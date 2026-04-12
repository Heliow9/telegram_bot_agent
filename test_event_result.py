from app.services.sportsdb_api import SportsDBAPI

api = SportsDBAPI()

fixture_id = "2398292"  # troque por qualquer fixture_id do predictions_log.json
result = api.get_event_result(fixture_id)

print(result)