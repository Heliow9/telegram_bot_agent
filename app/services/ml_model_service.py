from pathlib import Path
from typing import Optional, Dict, List, Any

import joblib
import pandas as pd


MODEL_PATH = Path("models/1x2_model.joblib")


EXPECTED_CLASSES = ("1", "X", "2")


class MLModelService:
    def __init__(self):
        self.model = None
        self.classes_: Optional[List[str]] = None
        self.features_: Optional[List[str]] = None
        self.metadata: Dict[str, Any] = {}
        self.market_type: str = "1x2"
        self._model_mtime: Optional[float] = None
        self._load()

    def _load(self):
        if not MODEL_PATH.exists():
            print("[ML] Modelo 1x2 ainda não encontrado.")
            self._model_mtime = None
            return

        try:
            payload = joblib.load(MODEL_PATH)
            self._model_mtime = MODEL_PATH.stat().st_mtime

            self.model = payload.get("model")
            self.classes_ = payload.get("classes")
            self.features_ = payload.get("features")
            self.metadata = payload.get("metadata") or {}
            self.market_type = str(self.metadata.get("market_type") or "1x2").strip().lower()

            if self.model is None or not self.classes_:
                print("[ML] Payload do modelo inválido.")
                self.model = None
                self.classes_ = None
                self.features_ = None
                self.metadata = {}
                self.market_type = "1x2"
                return

            if not self.features_:
                print("[ML] Modelo carregado sem lista de features. Inferência ficará insegura.")
                self.features_ = None

            print("[ML] Modelo 1x2 carregado com sucesso.")
            print(f"[ML] Market type: {self.market_type}")
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
            self.market_type = "1x2"

    def reload(self):
        """Recarrega o modelo do disco. Usado após treino manual/automático."""
        self.model = None
        self.classes_ = None
        self.features_ = None
        self.metadata = {}
        self.market_type = "1x2"
        self._model_mtime = None
        self._load()

    def refresh_if_changed(self):
        """Evita que o scheduler continue usando um modelo antigo em memória."""
        if not MODEL_PATH.exists():
            return
        try:
            current_mtime = MODEL_PATH.stat().st_mtime
        except Exception:
            return
        if self._model_mtime is None or current_mtime > self._model_mtime:
            print("[ML] Modelo alterado em disco. Recarregando para próximas análises.")
            self.reload()

    def is_available(self) -> bool:
        self.refresh_if_changed()
        return self.model is not None and self.classes_ is not None

    def get_metadata(self) -> Dict[str, Any]:
        self.refresh_if_changed()
        return self.metadata or {}

    def get_market_type(self) -> str:
        return self.market_type or "1x2"

    def _sanitize_features(self, features: Dict) -> Dict:
        if not isinstance(features, dict):
            return {}

        sanitized = {}

        for key, value in features.items():
            if value is None:
                sanitized[key] = 0.0
                continue

            if isinstance(value, bool):
                sanitized[key] = float(int(value))
                continue

            if isinstance(value, (int, float)):
                sanitized[key] = float(value)
                continue

            try:
                sanitized[key] = float(value)
            except (TypeError, ValueError):
                sanitized[key] = 0.0

        return sanitized

    def _build_aligned_dataframe(self, features: Dict) -> pd.DataFrame:
        safe_features = self._sanitize_features(features)
        raw_df = pd.DataFrame([safe_features])

        if self.features_:
            aligned = raw_df.reindex(columns=self.features_, fill_value=0.0)
            return aligned.fillna(0.0).astype(float)

        return raw_df.fillna(0.0).astype(float)

    def predict_proba(self, features: Dict) -> Optional[Dict[str, float]]:
        self.refresh_if_changed()
        if not self.is_available():
            return None

        try:
            df = self._build_aligned_dataframe(features)
            probs = self.model.predict_proba(df)[0]

            mapping = {}
            for label, prob in zip(self.classes_, probs):
                mapping[str(label)] = float(prob)

            result = {label: mapping.get(label, 0.0) for label in EXPECTED_CLASSES}

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

    def predict_label(self, features: Dict) -> Optional[str]:
        probabilities = self.predict_proba(features)
        if not probabilities:
            return None

        return max(probabilities, key=probabilities.get)

    def explain_prediction(self, features: Dict) -> Dict[str, Any]:
        probabilities = self.predict_proba(features)

        return {
            "available": self.is_available(),
            "market_type": self.get_market_type(),
            "classes": self.classes_ or [],
            "features_used": self.features_ or [],
            "probabilities": probabilities,
            "predicted_label": max(probabilities, key=probabilities.get) if probabilities else None,
        }