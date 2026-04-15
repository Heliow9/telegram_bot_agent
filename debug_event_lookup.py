import json
from app.services.sportsdb_api import SportsDBAPI

TEST_IDS = [
    "2451169",
    "2452577",
    "2453085",
]

api = SportsDBAPI()

for fixture_id in TEST_IDS:
    print("\n" + "=" * 100)
    print(f"FIXTURE ID: {fixture_id}")
    print("=" * 100)

    details = api.get_event_details(fixture_id)
    result = api.get_event_result(fixture_id)

    print("\n[DETAILS]")
    print(json.dumps(details, indent=2, ensure_ascii=False, default=str))

    print("\n[RESULT]")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))