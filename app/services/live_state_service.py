from pathlib import Path
from typing import Dict, Any
import json


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
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_fixture_state(self, fixture_id: str) -> Dict[str, Any]:
        state = self.load()
        return state.get(fixture_id, {})

    def update_fixture_state(self, fixture_id: str, fixture_state: Dict[str, Any]):
        state = self.load()
        state[fixture_id] = fixture_state
        self.save(state)