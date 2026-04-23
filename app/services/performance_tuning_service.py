from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


STORE_PATH = Path("data/predictions_log.json")


class PerformanceTuningService:
    """Reads resolved real-world results and builds lightweight tuning hints.

    It is intentionally file-based so it can operate even when the DB is under load.
    The service degrades gracefully when there is not enough historical data.
    """

    MIN_SAMPLE_PICK = 8
    MIN_SAMPLE_CONFIDENCE = 12
    MIN_SAMPLE_MARKET = 15
    MIN_SAMPLE_LEAGUE = 10

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or STORE_PATH
        self._cache_key: Optional[tuple[int, int]] = None
        self._cache: Optional[Dict] = None

    def _read_rows(self) -> List[Dict]:
        if not self.store_path.exists():
            return []

        try:
            raw = self.store_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            return []

        if not isinstance(data, list):
            return []

        return data

    @staticmethod
    def _is_resolved(row: Dict) -> bool:
        status = str(row.get("status") or "").strip().lower()
        result = str(row.get("result") or "").strip().lower()
        return status in {"hit", "miss"} or result in {"hit", "miss"}

    @staticmethod
    def _is_hit(row: Dict) -> bool:
        status = str(row.get("status") or "").strip().lower()
        result = str(row.get("result") or "").strip().lower()
        return status == "hit" or result == "hit"

    @staticmethod
    def _normalize_confidence(value: Optional[str]) -> str:
        text = str(value or "").strip().lower()
        return text or "desconhecida"

    @staticmethod
    def _normalize_market(value: Optional[str]) -> str:
        text = str(value or "").strip().lower()
        return text or "1x2"

    @staticmethod
    def _normalize_pick(value: Optional[str]) -> str:
        return str(value or "").strip().upper()

    def _rate(self, rows: List[Dict]) -> Dict[str, float | int]:
        total = len(rows)
        hits = sum(1 for row in rows if self._is_hit(row))
        misses = total - hits
        accuracy = round(hits / total, 4) if total else 0.0
        return {
            "total": total,
            "hits": hits,
            "misses": misses,
            "accuracy": accuracy,
        }

    def build_snapshot(self) -> Dict:
        try:
            stat = self.store_path.stat()
            cache_key = (int(stat.st_mtime), int(stat.st_size))
        except FileNotFoundError:
            cache_key = (0, 0)

        if self._cache_key == cache_key and self._cache is not None:
            return self._cache

        rows = [row for row in self._read_rows() if self._is_resolved(row)]

        by_confidence: Dict[str, List[Dict]] = {}
        by_market: Dict[str, List[Dict]] = {}
        by_pick: Dict[str, List[Dict]] = {}
        by_league: Dict[str, List[Dict]] = {}

        for row in rows:
            confidence = self._normalize_confidence(row.get("confidence"))
            market = self._normalize_market(row.get("market_type"))
            pick = self._normalize_pick(row.get("pick"))
            league = str(row.get("league") or row.get("league_name") or "Sem liga").strip() or "Sem liga"

            by_confidence.setdefault(confidence, []).append(row)
            by_market.setdefault(market, []).append(row)
            if pick:
                by_pick.setdefault(pick, []).append(row)
            by_league.setdefault(league, []).append(row)

        snapshot = {
            "summary": self._rate(rows),
            "by_confidence": {key: self._rate(value) for key, value in by_confidence.items()},
            "by_market": {key: self._rate(value) for key, value in by_market.items()},
            "by_pick": {key: self._rate(value) for key, value in by_pick.items()},
            "by_league": {key: self._rate(value) for key, value in by_league.items()},
        }

        self._cache_key = cache_key
        self._cache = snapshot
        return snapshot

    def market_adjustment(self, market_type: Optional[str]) -> float:
        stats = self.build_snapshot().get("by_market", {})
        item = stats.get(self._normalize_market(market_type)) or {}
        total = int(item.get("total") or 0)
        accuracy = float(item.get("accuracy") or 0.0)
        if total < self.MIN_SAMPLE_MARKET:
            return 0.0
        return max(min((accuracy - 0.5) * 0.12, 0.035), -0.035)

    def pick_adjustment(self, pick: Optional[str]) -> float:
        stats = self.build_snapshot().get("by_pick", {})
        item = stats.get(self._normalize_pick(pick)) or {}
        total = int(item.get("total") or 0)
        accuracy = float(item.get("accuracy") or 0.0)
        if total < self.MIN_SAMPLE_PICK:
            return 0.0
        return max(min((accuracy - 0.5) * 0.10, 0.03), -0.03)

    def confidence_adjustment(self, confidence: Optional[str]) -> float:
        stats = self.build_snapshot().get("by_confidence", {})
        item = stats.get(self._normalize_confidence(confidence)) or {}
        total = int(item.get("total") or 0)
        accuracy = float(item.get("accuracy") or 0.0)
        if total < self.MIN_SAMPLE_CONFIDENCE:
            return 0.0
        return max(min((accuracy - 0.5) * 0.08, 0.025), -0.025)

    def league_adjustment(self, league_name: Optional[str]) -> float:
        stats = self.build_snapshot().get("by_league", {})
        item = stats.get(str(league_name or "Sem liga").strip() or "Sem liga") or {}
        total = int(item.get("total") or 0)
        accuracy = float(item.get("accuracy") or 0.0)
        if total < self.MIN_SAMPLE_LEAGUE:
            return 0.0
        return max(min((accuracy - 0.5) * 0.08, 0.02), -0.02)

    def reliability_state(self) -> Dict:
        snapshot = self.build_snapshot()
        summary = snapshot.get("summary", {})
        total = int(summary.get("total") or 0)
        accuracy = float(summary.get("accuracy") or 0.0)

        if total < 20:
            level = "low"
            label = "Base histórica pequena"
        elif accuracy >= 0.56:
            level = "good"
            label = "Histórico favorável"
        elif accuracy >= 0.5:
            level = "medium"
            label = "Histórico neutro"
        else:
            level = "warning"
            label = "Histórico pede cautela"

        return {
            "level": level,
            "label": label,
            "resolved_total": total,
            "accuracy": accuracy,
        }
