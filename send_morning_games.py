from datetime import datetime
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import filter_morning_events
from app.services.message_formatter import format_games_summary
from app.services.telegram_service import TelegramService

api = SportsDBAPI()
analysis_service = AnalysisService()
telegram = TelegramService()

today = datetime.now().strftime("%Y-%m-%d")
league_name = "Brazilian Serie A"

events = api.get_events_by_day_list(today, league_name)
morning_events = filter_morning_events(events)
payloads = analysis_service.build_many_analyses(morning_events, default_league_name=league_name)

text = format_games_summary("🌅 Jogos da manhã - Brasileirão", payloads)
result = telegram.send_message(text)
print(result)