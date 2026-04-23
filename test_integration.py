from app.services.telegram_service import TelegramService
from app.services.odds_service import OddsService


def test_telegram():
    print("\n=== TESTE TELEGRAM ===")

    telegram = TelegramService()

    msg = """
📊 TESTE DO BOT

⚽ Flamengo x Palmeiras
🕒 21:30

🎯 Palpite: Casa (1)
🔒 Confiança: Alta

📉 Odds
• Casa: 1.85
• Empate: 3.40
• Fora: 4.20
"""

    try:
        result = telegram.send_message(msg)
        print("Chat principal:", result)

        # testa canal também
        result_channel = telegram.send_message(msg)
        print("Canal:", result_channel)

    except Exception as e:
        print("Erro Telegram:", e)


def test_odds():
    print("\n=== TESTE ODDS ===")

    odds_service = OddsService()

    odds = odds_service.get_match_odds(
        home_team="Arsenal",
        away_team="Chelsea",
        league_name="Premier League",
    )

    if odds:
        print("Odds encontradas:")
        print(odds)
    else:
        print("Nenhuma odd encontrada")


if __name__ == "__main__":
    test_telegram()
    test_odds()