from pathlib import Path
from typing import Dict, Any
import json

from app.services.json_lock_store import locked_json


LIVE_STATE_PATH = Path("data/live_state.json")


class LiveStateService:
    def __init__(self, path: Path = LIVE_STATE_PATH):
        self.path = path
        self._ensure_store()

    def _ensure_store(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def load(self) -> Dict[str, Any]:
        self._ensure_store()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def save(self, data: Dict[str, Any]):
        self._ensure_store()
        with locked_json(self.path, dict) as state:
            state.clear()
            state.update(data or {})

    def get_fixture_state(self, fixture_id: str) -> Dict[str, Any]:
        state = self.load()
        return state.get(str(fixture_id), {})

    def update_fixture_state(self, fixture_id: str, fixture_state: Dict[str, Any]):
        fixture_id = str(fixture_id)
        with locked_json(self.path, dict) as state:
            state[fixture_id] = fixture_state

    def claim_checkpoint(self, fixture_id: str, checkpoint: int) -> bool:
        """Reserva checkpoint live de forma atômica entre processos."""
        fixture_id = str(fixture_id)
        with locked_json(self.path, dict) as state:
            current = state.get(fixture_id, {}) or {}
            sent = current.get("sent_checkpoints", []) or []
            if checkpoint in sent:
                return False
            current["sent_checkpoints"] = sorted(set(sent + [checkpoint]))
            state[fixture_id] = current
            return True
