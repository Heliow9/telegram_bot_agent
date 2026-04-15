from app.services.daily_leagues_service import DailyLeaguesService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import (
    format_best_pick,
    format_top_ranking,
    format_league_summary,
    group_payloads_by_league,
)
from app.services.prediction_store import save_prediction

print("🚀 TESTE MANUAL - PRÉ-JOGO TARDE/NOITE\n")

daily_service = DailyLeaguesService()
telegram = TelegramService()

try:
    payloads = daily_service.get_afternoon_payloads()
    print(f"📊 Jogos encontrados: {len(payloads)}")
except Exception as e:
    print(f"❌ Erro ao buscar jogos: {e}")
    raise SystemExit(1)

if not payloads:
    print("📭 Nenhum jogo encontrado para hoje.")
    telegram.send_message(
        "📭 *Nenhum jogo encontrado para a tarde/noite hoje.*\n\n"
        "Ligas monitoradas: Brasileirão, Premier League, Champions, etc."
    )
    raise SystemExit(0)

print("\n💾 Persistindo previsões...")
for payload in payloads:
    try:
        save_prediction(payload)
    except Exception as e:
        fixture = payload.get("fixture", {})
        print(f"❌ Erro ao salvar fixture={fixture.get('id')}: {e}")

print("\n🔥 Enviando melhor aposta...")
telegram.send_message(format_best_pick(payloads[0]))

print("📊 Enviando top ranking...")
telegram.send_message(format_top_ranking(payloads, top_n=5))

grouped = group_payloads_by_league(payloads)

desired_order = [
    "Brasileirão Série A",
    "Brasileirão Série B",
    "Premier League",
    "Championship",
    "Liga dos Campeões",
    "Argentina Liga Profesional",
    "Itália Série A",
    "Turquia Super Lig",
    "Libertadores",
    "Copa Sul-Americana",
]

print("\n📨 Enviando resumos por liga...")
for league_name in desired_order:
    league_payloads = grouped.get(league_name, [])
    if not league_payloads:
        continue

    print(f"➡️ {league_name} ({len(league_payloads)} jogos)")
    telegram.send_message(
        format_league_summary(league_name, league_payloads)
    )

print("\n✅ TESTE FINALIZADO COM SUCESSO")
print("ℹ️ Depois que os jogos terminarem, rode: python check_results.py")