from pathlib import Path
from typing import Optional, Dict, List, Any

import joblib
import pandas as pd


MODEL_PATH = Path("models/1x2_model.joblib")


class MLModelService:
    def __init__(self):
        self.model = None
        self.classes_: Optional[List[str]] = None
        self.features_: Optional[List[str]] = None
        self.metadata: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if not MODEL_PATH.exists():
            print("[ML] Modelo 1x2 ainda não encontrado.")
            return

        try:
            payload = joblib.load(MODEL_PATH)

            self.model = payload.get("model")
            self.classes_ = payload.get("classes")
            self.features_ = payload.get("features")
            self.metadata = payload.get("metadata") or {}

            if not self.model or not self.classes_:
                print("[ML] Payload do modelo inválido.")
                self.model = None
                self.classes_ = None
                self.features_ = None
                self.metadata = {}
                return

            if not self.features_:
                print("[ML] Modelo carregado sem lista de features. Inferência ficará insegura.")
                self.features_ = None

            print("[ML] Modelo 1x2 carregado com sucesso.")
            print(f"[ML] Classes: {self.classes_}")
            if self.features_:
                print(f"[ML] Total de features: {len(self.features_)}")

            if self.metadata:
                print(
                    "[ML] Metadata | "
                    f"rows={self.metadata.get('rows')} | "
                    f"accuracy={self.metadata.get('accuracy')} | "
                    f"log_loss={self.metadata.get('log_loss')}"
                )

        except Exception as e:
            print(f"[ML] Erro ao carregar modelo: {e}")
            self.model = None
            self.classes_ = None
            self.features_ = None
            self.metadata = {}

    def is_available(self) -> bool:
        return self.model is not None and self.classes_ is not None

    def get_metadata(self) -> Dict[str, Any]:
        return self.metadata or {}

    def _build_aligned_dataframe(self, features: Dict) -> pd.DataFrame:
        raw_df = pd.DataFrame([features or {}])

        if self.features_:
            aligned = raw_df.reindex(columns=self.features_, fill_value=0)
            return aligned

        return raw_df.fillna(0)

    def predict_proba(self, features: Dict) -> Optional[Dict[str, float]]:
        if not self.is_available():
            return None

        try:
            df = self._build_aligned_dataframe(features)
            probs = self.model.predict_proba(df)[0]

            mapping = {}
            for label, prob in zip(self.classes_, probs):
                mapping[str(label)] = float(prob)

            result = {
                "1": mapping.get("1", 0.0),
                "X": mapping.get("X", 0.0),
                "2": mapping.get("2", 0.0),
            }

            total = result["1"] + result["X"] + result["2"]
            if total > 0:
                result = {
                    "1": result["1"] / total,
                    "X": result["X"] / total,
                    "2": result["2"] / total,
                }

            return result

        except Exception as e:
            print(f"[ML] Erro ao prever probabilidades: {e}")
            return None