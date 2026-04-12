from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import filter_events_starting_in_30_minutes
from app.services.message_formatter import format_prediction_message
from app.services.telegram_service import TelegramService

api = SportsDBAPI()
analysis_service = AnalysisService()
telegram = TelegramService()

today = datetime.now().strftime("%Y-%m-%d")
league_name = "Brazilian Serie A"

events = api.get_events_by_day_list(today, league_name)
starting_soon = filter_events_starting_in_30_minutes(events, tolerance_minutes=5)

if not starting_soon:
    print("Nenhum jogo começando em cerca de 30 minutos.")
else:
    for match in starting_soon:
        payload = analysis_service.build_match_analysis(match, default_league_name=league_name)
        if not payload:
            continue

        text = format_prediction_message(payload)
        result = telegram.send_message(text)
        print(result)