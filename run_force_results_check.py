from app.services.result_checker_service import ResultCheckerService
from app.services.gemini_summary_service import GeminiSummaryService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import format_result_message, pick_winner_photo_url


def main():
    print("🚀 FORÇANDO CHECAGEM DE RESULTADOS\n")

    checker = ResultCheckerService()
    gemini = GeminiSummaryService()
    telegram = TelegramService()

    try:
        updates = checker.check_pending_predictions()
        print(f"🏁 Jogos finalizados encontrados: {len(updates)}")
    except Exception as e:
        print(f"❌ Erro ao checar resultados: {e}")
        return

    if not updates:
        print("ℹ️ Nenhum resultado novo encontrado.")
        return

    for item in updates:
        try:
            ai_summary = gemini.build_result_summary(item)
            caption = format_result_message(item, ai_summary=ai_summary)
            photo_url = pick_winner_photo_url(item)

            print(
                f"📌 {item.get('home_team')} x {item.get('away_team')} | "
                f"Status: {item.get('status')} | "
                f"Placar: {item.get('home_score')} x {item.get('away_score')}"
            )

            if photo_url:
                result = telegram.send_photo(photo_url, caption=caption)
            else:
                result = telegram.send_message(caption)

            print(f"📨 Retorno Telegram: {result}")

        except Exception as e:
            print(
                f"❌ Erro ao enviar resultado de "
                f"{item.get('home_team')} x {item.get('away_team')}: {e}"
            )

    print("\n✅ CHECAGEM FINALIZADA")
    

if __name__ == "__main__":
    main()