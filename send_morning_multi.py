from app.services.daily_leagues_service import DailyLeaguesService
from app.services.message_formatter import (
    format_best_pick,
    format_top_ranking,
    format_league_summary,
    group_payloads_by_league,
)
from app.services.telegram_service import TelegramService

daily_service = DailyLeaguesService()
telegram = TelegramService()

payloads = daily_service.get_morning_payloads()

if not payloads:
    result = telegram.send_message("🌅 *Palpites da manhã*\n\nNenhum jogo encontrado.")
    print(result)
else:
    result = telegram.send_message(format_best_pick(payloads[0]))
    print(result)

    result = telegram.send_message(format_top_ranking(payloads, top_n=5))
    print(result)

    grouped = group_payloads_by_league(payloads)

    desired_order = [
        "Brasileirão Série A",
        "Brasileirão Série B",
        "Premier League",
    ]

    for league_name in desired_order:
        league_payloads = grouped.get(league_name, [])
        if not league_payloads:
            continue

        result = telegram.send_message(
            format_league_summary(league_name, league_payloads)
        )
        print(result)