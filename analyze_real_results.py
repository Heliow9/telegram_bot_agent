from app.services.performance_tuning_service import PerformanceTuningService

service = PerformanceTuningService()
snapshot = service.build_snapshot()
reliability = service.reliability_state()

print("\n=== LEITURA DOS RESULTADOS REAIS ===\n")
print(f"Status: {reliability['label']}")
print(f"Base resolvida: {reliability['resolved_total']}")
print(f"Accuracy histórica: {reliability['accuracy']:.2%}\n")

print("--- Por mercado ---")
for market, item in sorted(snapshot.get('by_market', {}).items()):
    print(f"{market}: total={item['total']} hits={item['hits']} acc={item['accuracy']:.2%}")

print("\n--- Por pick ---")
for pick, item in sorted(snapshot.get('by_pick', {}).items()):
    print(f"{pick}: total={item['total']} hits={item['hits']} acc={item['accuracy']:.2%}")

print("\n--- Por confiança ---")
for conf, item in sorted(snapshot.get('by_confidence', {}).items()):
    print(f"{conf}: total={item['total']} hits={item['hits']} acc={item['accuracy']:.2%}")
    
    
    
