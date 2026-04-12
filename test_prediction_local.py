from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI
from app.services.predictor import extract_team_form, calculate_prediction
from app.services.message_formatter import format_prediction_message

api = SportsDBAPI()

LEAGUE_NAME = "Brazilian Serie A"
today = datetime.now().strftime("%Y-%m-%d")

events = api.get_events_by_day_list(today, LEAGUE_NAME)

if not events:
    print("Nenhum jogo encontrado hoje.")
else:
    match = events[0]

    home_team = match.get("strHomeTeam")
    away_team = match.get("strAwayTeam")
    home_team_id = match.get("idHomeTeam")
    away_team_id = match.get("idAwayTeam")

    home_last = api.get_team_last_events_list(home_team_id)
    away_last = api.get_team_last_events_list(away_team_id)

    home_form = extract_team_form(home_last, home_team)
    away_form = extract_team_form(away_last, away_team)

    analysis = calculate_prediction(home_team, away_team, home_form, away_form)

    payload = {
        "fixture": {
            "league": match.get("strLeague", LEAGUE_NAME),
            "home_team": home_team,
            "away_team": away_team,
            "date": match.get("dateEvent", ""),
            "time": match.get("strTime", ""),
        },
        "analysis": analysis,
    }

    text = format_prediction_message(payload)
    print(text)