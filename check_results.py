from app.services.result_checker_service import ResultCheckerService
from app.services.prediction_store import get_pending_predictions

checker = ResultCheckerService()

pending = get_pending_predictions()
print(f"Previsões pendentes encontradas: {len(pending)}")

updates = checker.check_pending_predictions()

if not updates:
    print("\nNenhum resultado final novo encontrado.")
else:
    print("\nResultados atualizados:\n")
    for item in updates:
        print(
            f"{item['home_team']} x {item['away_team']} | "
            f"pick={item['pick']} | "
            f"resultado={item['real_result']} | "
            f"placar={item['home_score']}-{item['away_score']} | "
            f"status={item['status']}"
        )

print("\nEstatísticas atuais:\n")
stats = checker.get_stats()
print(stats)