from app.services.training_dataset_service import TrainingDatasetService
from app.services.ml_training_service import MLTrainingService

print("🚀 INICIANDO TREINO MANUAL")

training_dataset_service = TrainingDatasetService()
ml_training_service = MLTrainingService()

rows_added = training_dataset_service.append_resolved_predictions_to_dataset()

print(f"📊 Linhas adicionadas ao dataset: {rows_added}")

if rows_added > 0:
    ml_training_service.train()
    print("🤖 Modelo treinado com sucesso!")
else:
    print("⚠️ Nenhuma linha nova. Modelo NÃO foi re-treinado.")

print("✅ FINALIZADO")