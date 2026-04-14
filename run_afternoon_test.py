from app.services.daily_leagues_service import DailyLeaguesService
from app.services.telegram_service import TelegramService
from app.services.message_formatter import (
    format_prediction_message,
    format_best_pick,
    format_top_ranking,
    format_league_summary,
    group_payloads_by_league,
)

print("🚀 TESTE MANUAL - PRÉ-JOGO TARDE/NOITE\n")

daily_service = DailyLeaguesService()
telegram = TelegramService()

try:
    payloads = daily_service.get_afternoon_payloads()
    print(f"📊 Jogos encontrados: {len(payloads)}")
except Exception as e:
    print(f"❌ Erro ao buscar jogos: {e}")
    exit()

# 🚫 fallback se não tiver jogos
if not payloads:
    print("📭 Nenhum jogo encontrado para hoje.")
    telegram.send_message(
        "📭 *Nenhum jogo encontrado para a tarde/noite hoje.*\n\n"
        "Ligas monitoradas: Brasileirão, Premier League, Champions, etc."
    )
    exit()

# 🔥 Melhor pick
print("\n🔥 Enviando melhor aposta...")
telegram.send_message(format_best_pick(payloads[0]))

# 📊 Top ranking
print("📊 Enviando top ranking...")
telegram.send_message(format_top_ranking(payloads, top_n=5))

# 🏆 Agrupar por liga
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

# 📨 Enviar por liga
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