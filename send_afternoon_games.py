from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import filter_afternoon_events
from app.services.message_formatter import format_games_summary
from app.services.telegram_service import TelegramService

api = SportsDBAPI()
analysis_service = AnalysisService()
telegram = TelegramService()

today = datetime.now().strftime("%Y-%m-%d")
league_name = "Brazilian Serie A"

events = api.get_events_by_day_list(today, league_name)
afternoon_events = filter_afternoon_events(events)
payloads = analysis_service.build_many_analyses(afternoon_events, default_league_name=league_name)

text = format_games_summary("☀️ Jogos da tarde/noite - Brasileirão", payloads)
result = telegram.send_message(text)
print(result)