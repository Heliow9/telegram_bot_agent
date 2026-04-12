from app.services.daily_leagues_service import DailyLeaguesService
from app.services.message_formatter import format_prediction_message
from app.services.telegram_service import TelegramService

daily_service = DailyLeaguesService()
telegram = TelegramService()

payloads = daily_service.get_30min_payloads()

if not payloads:
    print("Nenhum jogo começa em cerca de 30 minutos.")
else:
    for payload in payloads:
        text = format_prediction_message(payload)
        result = telegram.send_message(text)
        print(result)