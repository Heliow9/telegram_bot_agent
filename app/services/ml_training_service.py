from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


TRAINING_DATA_PATH = Path("data/historical_training_matches.csv")
MODEL_PATH = Path("models/1x2_model.joblib")
METADATA_PATH = Path("models/1x2_model_metadata.json")


class MLTrainingService:
    MIN_ROWS = 60
    MIN_CLASSES = 2
    TEST_SIZE = 0.25
    RANDOM_STATE = 42

    def _build_model(self) -> Pipeline:
        return Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ("clf", LogisticRegression(
                solver="lbfgs",
                max_iter=1000,
                class_weight="balanced",
                multi_class="auto",
            )),
        ])

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

        if len(df) < self.MIN_ROWS:
            print(
                f"[ML TRAIN] Dataset pequeno demais para treino confiável. "
                f"Linhas atuais: {len(df)} | mínimo recomendado: {self.MIN_ROWS}"
            )
            return

        class_counts = y.value_counts().to_dict()
        if y.nunique() < self.MIN_CLASSES:
            print("[ML TRAIN] É necessário ter pelo menos 2 classes no dataset.")
            return

        print(f"[ML TRAIN] Linhas totais: {len(df)}")
        print(f"[ML TRAIN] Classes: {class_counts}")
        print(f"[ML TRAIN] Features usadas: {list(X.columns)}")

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=self.TEST_SIZE,
                random_state=self.RANDOM_STATE,
                stratify=y if y.nunique() > 1 else None,
            )
        except ValueError as e:
            print(f"[ML TRAIN] Falha no split estratificado: {e}")
            print("[ML TRAIN] Treino cancelado para evitar modelo ruim.")
            return

        model = self._build_model()
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)

        acc = accuracy_score(y_test, y_pred)
        try:
            ll = log_loss(y_test, y_prob, labels=list(model.classes_))
        except Exception:
            ll = None

        metadata = {
            "rows": int(len(df)),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "classes": list(model.classes_),
            "class_distribution": class_counts,
            "features": list(X.columns),
            "accuracy": round(float(acc), 4),
            "log_loss": round(float(ll), 4) if ll is not None else None,
        }

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": model,
                "classes": list(model.classes_),
                "features": list(X.columns),
                "metadata": metadata,
            },
            MODEL_PATH,
        )

        METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        METADATA_PATH.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"[ML TRAIN] Modelo salvo em {MODEL_PATH}")
        print(f"[ML TRAIN] Metadata salva em {METADATA_PATH}")
        print(
            f"[ML TRAIN] Métricas | accuracy={metadata['accuracy']} | "
            f"log_loss={metadata['log_loss']}"
        )