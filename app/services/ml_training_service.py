from pathlib import Path
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression


TRAINING_DATA_PATH = Path("data/historical_training_matches.csv")
MODEL_PATH = Path("models/1x2_model.joblib")


class MLTrainingService:
    def train(self):
        if not TRAINING_DATA_PATH.exists():
            print("[ML TRAIN] Dataset não encontrado.")
            return

        df = pd.read_csv(TRAINING_DATA_PATH)

        if df.empty:
            print("[ML TRAIN] Dataset vazio.")
            return

        if "target" not in df.columns:
            print("[ML TRAIN] Coluna target não encontrada.")
            return

        drop_cols = [
            "target",
            "league",
            "fixture_id",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
        ]

        X = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        y = df["target"].astype(str)

        if X.empty:
            print("[ML TRAIN] Nenhuma feature disponível para treino.")
            return

        if y.nunique() < 2:
            print("[ML TRAIN] É necessário ter pelo menos 2 classes no dataset.")
            return

        model = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ("clf", LogisticRegression(
                solver="lbfgs",
                max_iter=1000,
                class_weight="balanced",
            )),
        ])

        model.fit(X, y)

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": model,
                "classes": list(model.classes_),
                "features": list(X.columns),
            },
            MODEL_PATH,
        )

        print(f"[ML TRAIN] Modelo salvo em {MODEL_PATH}")