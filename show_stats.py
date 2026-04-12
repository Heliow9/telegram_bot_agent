from app.services.prediction_store import build_stats

stats = build_stats()

print("\n=== ESTATÍSTICAS DO MODELO ===\n")
print(f"Total de previsões: {stats['total_predictions']}")
print(f"Resolvidas: {stats['resolved_predictions']}")
print(f"Acertos: {stats['hits']}")
print(f"Erros: {stats['misses']}")
print(f"Acurácia geral: {stats['accuracy']:.2%}")

print("\n--- Por confiança ---")
for conf, values in stats["by_confidence"].items():
    print(
        f"{conf}: total={values['total']} | "
        f"hits={values['hits']} | "
        f"acc={values['accuracy']:.2%}"
    )

print("\n--- Por liga ---")
for league, values in stats["by_league"].items():
    print(
        f"{league}: total={values['total']} | "
        f"hits={values['hits']} | "
        f"acc={values['accuracy']:.2%}"
    )