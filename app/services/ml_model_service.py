from pathlib import Path
from typing import Optional, Dict
import pandas as pd
import joblib


MODEL_PATH = Path("models/1x2_model.joblib")


class MLModelService:
    def __init__(self):
        self.model = None
        self.classes_ = None
        self._load()

    def _load(self):
        if not MODEL_PATH.exists():
            return

        try:
            payload = joblib.load(MODEL_PATH)
            self.model = payload.get("model")
            self.classes_ = payload.get("classes")
            print("[ML] Modelo 1x2 carregado com sucesso.")
        except Exception as e:
            print(f"[ML] Erro ao carregar modelo: {e}")
            self.model = None
            self.classes_ = None

    def is_available(self) -> bool:
        return self.model is not None and self.classes_ is not None

    def predict_proba(self, features: Dict) -> Optional[Dict[str, float]]:
        if not self.is_available():
            return None

        try:
            df = pd.DataFrame([features])
            probs = self.model.predict_proba(df)[0]

            mapping = {}
            for label, prob in zip(self.classes_, probs):
                mapping[str(label)] = float(prob)

            return {
                "1": mapping.get("1", 0.0),
                "X": mapping.get("X", 0.0),
                "2": mapping.get("2", 0.0),
            }
        except Exception as e:
            print(f"[ML] Erro ao prever probabilidades: {e}")
            return None