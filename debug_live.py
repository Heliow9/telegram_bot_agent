from app.services.football_api_service import FootballAPIService

api = FootballAPIService()

print("=== TESTE LIVE ===")
fixtures = api.get_live_fixtures()
print("TOTAL LIVE:", len(fixtures))

print("\n=== TESTE POR DATA PREMIER LEAGUE ===")
fixtures_by_date = api.get_fixtures_by_date(
    date_str="2026-04-13",
    league_id=39,   # Premier League na API-Football
    season="2025"
)
print("TOTAL DATE:", len(fixtures_by_date))

for item in fixtures_by_date[:10]:
    league = item.get("league", {}).get("name")
    home = item.get("teams", {}).get("home", {}).get("name")
    away = item.get("teams", {}).get("away", {}).get("name")
    status = item.get("fixture", {}).get("status", {}).get("short")
    fixture_id = item.get("fixture", {}).get("id")
    print(f"{fixture_id} | {league} | {home} x {away} | {status}")