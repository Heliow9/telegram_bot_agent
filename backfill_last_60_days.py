import time
from app.services.historical_backfill_service import HistoricalBackfillService
from app.services.training_dataset_service import TrainingDatasetService
from app.services.ml_training_service import MLTrainingService


def main():
    backfill = HistoricalBackfillService()
    training_dataset = TrainingDatasetService()
    trainer = MLTrainingService()

    events = backfill.get_all_recent_finished_events()
    print(f"[BACKFILL] Total de jogos encontrados: {len(events)}")

    rows = []
    for i, event in enumerate(events, start=1):
        league_meta = event.get("_league_meta")
        if not league_meta:
            continue

        try:
            row = training_dataset.build_training_row(event, league_meta)
            if row:
                rows.append(row)

            print(f"[BACKFILL] Processado {i}/{len(events)}")
            time.sleep(0.5)
        except Exception as e:
            print(f"[BACKFILL] Erro gerando linha {event.get('idEvent')}: {e}")

    print(f"[BACKFILL] Linhas de treino geradas: {len(rows)}")
    training_dataset.save_rows(rows)
    trainer.train()


if __name__ == "__main__":
    main()