from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.services.time_utils import now_local


TRAINING_DATA_PATH = Path("data/historical_training_matches.csv")
MODEL_PATH = Path("models/1x2_model.joblib")
METADATA_PATH = Path("models/1x2_model_metadata.json")


class MLTrainingService:
    MIN_ROWS = 20
    MIN_CLASSES = 2
    TEST_SIZE = 0.25
    RANDOM_STATE = 42

    def _build_model(self) -> Pipeline:
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
                (
                    "clf",
                    LogisticRegression(
                        solver="lbfgs",
                        max_iter=1500,
                        class_weight="balanced",
                        multi_class="auto",
                    ),
                ),
            ]
        )

    def _can_use_stratify(self, y: pd.Series) -> bool:
        counts = y.value_counts()
        if counts.empty:
            return False
        return counts.min() >= 2

    def _normalize_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        if "target" not in df.columns:
            return df

        df["target"] = df["target"].astype(str).str.strip().str.upper()

        # compatibilidade com futuros mercados
        # se no futuro existir market_type e market_target, o treino ainda funciona
        if "market_type" not in df.columns:
            df["market_type"] = "1x2"

        df["market_type"] = (
            df["market_type"]
            .astype(str)
            .str.strip()
            .str.lower()
            .replace("", "1x2")
        )

        # por enquanto este trainer continua treinando apenas 1x2
        df = df[df["market_type"] == "1x2"].copy()

        valid_targets = {"1", "X", "2"}
        df = df[df["target"].isin(valid_targets)].copy()

        return df

    def _drop_non_feature_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        drop_cols = [
            "target",
            "market_target",
            "market_type",
            "league",
            "fixture_id",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "created_at",
            "checked_at",
            "started_at",
            "finished_at",
            "last_checked_at",
            "result_source",
            "last_status_text",
            "pick",
            "result",
            "status",
        ]

        return df.drop(
            columns=[col for col in drop_cols if col in df.columns],
            errors="ignore",
        )

    def train(self):
        if not TRAINING_DATA_PATH.exists():
            print("[ML TRAIN] Dataset não encontrado.")
            return

        try:
            df = pd.read_csv(TRAINING_DATA_PATH)
        except Exception as e:
            print(f"[ML TRAIN] Erro ao ler dataset: {e}")
            return

        if df.empty:
            print("[ML TRAIN] Dataset vazio.")
            return

        if "target" not in df.columns:
            print("[ML TRAIN] Coluna target não encontrada.")
            return

        df = self._normalize_dataset(df)

        if df.empty:
            print("[ML TRAIN] Dataset sem linhas válidas após normalização.")
            return

        X = self._drop_non_feature_columns(df)
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

        print(f"[ML TRAIN] Linhas totais válidas: {len(df)}")
        print(f"[ML TRAIN] Classes: {class_counts}")
        print(f"[ML TRAIN] Features usadas: {list(X.columns)}")

        use_stratify = self._can_use_stratify(y)
        if not use_stratify:
            print(
                "[ML TRAIN] Split sem estratificação: há classes com menos de 2 exemplos."
            )

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=self.TEST_SIZE,
                random_state=self.RANDOM_STATE,
                stratify=y if use_stratify else None,
            )
        except ValueError as e:
            print(f"[ML TRAIN] Falha no split: {e}")
            print("[ML TRAIN] Treino cancelado para evitar modelo ruim.")
            return

        train_class_counts = y_train.value_counts().to_dict()
        test_class_counts = y_test.value_counts().to_dict()

        if len(set(y_train.unique())) < 2:
            print(
                "[ML TRAIN] Treino cancelado: conjunto de treino ficou com menos de 2 classes."
            )
            return

        model = self._build_model()
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)

        acc = accuracy_score(y_test, y_pred)

        try:
            ll = log_loss(y_test, y_prob, labels=list(model.classes_))
        except Exception as e:
            print(f"[ML TRAIN] Não foi possível calcular log_loss: {e}")
            ll = None

        metadata = {
            "trained_at": now_local().isoformat(),
            "market_type": "1x2",
            "rows": int(len(df)),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "classes": list(model.classes_),
            "class_distribution": class_counts,
            "train_class_distribution": train_class_counts,
            "test_class_distribution": test_class_counts,
            "features": list(X.columns),
            "features_count": int(len(X.columns)),
            "accuracy": round(float(acc), 4),
            "log_loss": round(float(ll), 4) if ll is not None else None,
            "used_stratify": bool(use_stratify),
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
            f"log_loss={metadata['log_loss']} | stratify={metadata['used_stratify']}"
        )