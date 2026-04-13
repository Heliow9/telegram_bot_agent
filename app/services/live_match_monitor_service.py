from datetime import datetime
from typing import Dict, List, Optional

from app.constants import LEAGUES
from app.config import settings
from app.services.football_api_service import FootballAPIService
from app.services.gemini_summary_service import GeminiSummaryService
from app.services.live_signal_service import LiveSignalService
from app.services.live_state_service import LiveStateService
from app.services.telegram_service import TelegramService


class LiveMatchMonitorService:
    def __init__(self):
        self.football_api = FootballAPIService()
        self.telegram = TelegramService()
        self.gemini = GeminiSummaryService()
        self.state_service = LiveStateService()
        self.signal_service = LiveSignalService()

        self.league_map = {
            int(item["id"]): item
            for item in LEAGUES
            if str(item.get("id", "")).isdigit()
        }
        self.checkpoints = self._parse_checkpoints(settings.live_minute_checkpoints)

    def _parse_checkpoints(self, raw: str) -> List[int]:
        values = []
        for part in (raw or "").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(int(part))
            except ValueError:
                continue

        return sorted(set(values)) or [15, 30, 45, 60, 75]

    def _extract_stat(self, stats: List[Dict], team_side: str, stat_name: str, default="0"):
        for item in stats:
            statistics = item.get("statistics", [])
            is_home = team_side == "home" and item.get("_team_side") == "home"
            is_away = team_side == "away" and item.get("_team_side") == "away"

            if not (is_home or is_away):
                continue

            for stat in statistics:
                if stat.get("type") == stat_name:
                    value = stat.get("value")
                    return value if value is not None else default

        return default

    def _normalize_statistics(self, fixture: Dict, statistics: List[Dict]) -> Dict:
        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")

        normalized = []
        for item in statistics:
            team_id = item.get("team", {}).get("id")

            if team_id == home_id:
                team_side = "home"
            elif team_id == away_id:
                team_side = "away"
            else:
                team_side = "unknown"

            copy_item = dict(item)
            copy_item["_team_side"] = team_side
            normalized.append(copy_item)

        return {
            "home_possession": self._extract_stat(normalized, "home", "Ball Possession", "0"),
            "away_possession": self._extract_stat(normalized, "away", "Ball Possession", "0"),
            "home_shots": self._extract_stat(normalized, "home", "Total Shots", "0"),
            "away_shots": self._extract_stat(normalized, "away", "Total Shots", "0"),
            "home_shots_on_target": self._extract_stat(normalized, "home", "Shots on Goal", "0"),
            "away_shots_on_target": self._extract_stat(normalized, "away", "Shots on Goal", "0"),
            "home_corners": self._extract_stat(normalized, "home", "Corner Kicks", "0"),
            "away_corners": self._extract_stat(normalized, "away", "Corner Kicks", "0"),
            "home_red_cards": self._extract_stat(normalized, "home", "Red Cards", "0"),
            "away_red_cards": self._extract_stat(normalized, "away", "Red Cards", "0"),
        }

    def _get_last_goal_event(self, events: List[Dict]) -> Optional[Dict]:
        goal_types = {"Goal", "Own Goal", "Penalty"}
        valid = [e for e in events if e.get("type") in goal_types]
        if not valid:
            return None
        return valid[-1]

    def _checkpoint_to_send(self, minute: int, already_sent: List[int]) -> Optional[int]:
        for checkpoint in self.checkpoints:
            if minute >= checkpoint and checkpoint not in already_sent:
                return checkpoint
        return None

    def _build_snapshot(self, fixture: Dict, events: List[Dict], stats_map: Dict) -> Dict:
        fixture_meta = fixture.get("fixture", {})
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        league = fixture.get("league", {})
        status = fixture_meta.get("status", {})

        home_team = teams.get("home", {}).get("name", "Casa")
        away_team = teams.get("away", {}).get("name", "Fora")
        home_score = goals.get("home") or 0
        away_score = goals.get("away") or 0
        minute = status.get("elapsed") or 0

        signal, signal_reason = self.signal_service.evaluate({
            "home_shots": stats_map.get("home_shots"),
            "away_shots": stats_map.get("away_shots"),
            "home_shots_on_target": stats_map.get("home_shots_on_target"),
            "away_shots_on_target": stats_map.get("away_shots_on_target"),
            "home_possession": stats_map.get("home_possession"),
            "away_possession": stats_map.get("away_possession"),
            "home_red_cards": stats_map.get("home_red_cards"),
            "away_red_cards": stats_map.get("away_red_cards"),
        })

        last_goal = self._get_last_goal_event(events)

        return {
            "fixture_id": str(fixture_meta.get("id", "")),
            "league": league.get("name", "Jogo"),
            "league_id": league.get("id"),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": int(home_score),
            "away_score": int(away_score),
            "minute": int(minute),
            "status_short": status.get("short", ""),
            "status_long": status.get("long", ""),
            "timestamp": datetime.utcnow().isoformat(),
            "score_signature": f"{home_score}-{away_score}",
            "goal_signature": (
                f"{home_score}-{away_score}-{last_goal.get('time', {}).get('elapsed', minute)}"
                if last_goal else ""
            ),
            "scoring_team": (last_goal or {}).get("team", {}).get("name"),
            "scorer": (last_goal or {}).get("player", {}).get("name"),
            "last_goal_minute": (last_goal or {}).get("time", {}).get("elapsed"),
            "home_possession": stats_map.get("home_possession"),
            "away_possession": stats_map.get("away_possession"),
            "home_shots": stats_map.get("home_shots"),
            "away_shots": stats_map.get("away_shots"),
            "home_shots_on_target": stats_map.get("home_shots_on_target"),
            "away_shots_on_target": stats_map.get("away_shots_on_target"),
            "home_corners": stats_map.get("home_corners"),
            "away_corners": stats_map.get("away_corners"),
            "home_red_cards": stats_map.get("home_red_cards"),
            "away_red_cards": stats_map.get("away_red_cards"),
            "live_signal": signal,
            "signal_reason": signal_reason,
            "sent_checkpoints": [],
        }

    def _is_monitored_league(self, fixture: Dict) -> bool:
        league_id = fixture.get("league", {}).get("id")
        try:
            return int(league_id) in self.league_map
        except (TypeError, ValueError):
            return False

    def _send_goal_alert(self, snapshot: Dict):
        ai_text = self.gemini.build_live_goal_summary(snapshot)

        if ai_text:
            text = (
                f"⚽ {snapshot['league']}\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x {snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"{ai_text}"
            )
        else:
            scorer_text = f" {snapshot['scorer']}" if snapshot.get("scorer") else ""
            team_text = snapshot.get("scoring_team") or "Time não identificado"
            text = (
                f"⚽ {snapshot['league']}\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x {snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"Gol de {team_text}{scorer_text} aos {snapshot.get('last_goal_minute') or snapshot['minute']} minutos."
            )

        result = self.telegram.send_message(text)
        print(f"[LIVE] Alerta de gol enviado: {result}")

    def _send_checkpoint_alert(self, snapshot: Dict, checkpoint: int):
        ai_text = self.gemini.build_live_checkpoint_summary(snapshot)

        signal_emoji = {
            "casa_favorável": "📈",
            "fora_favorável": "📉",
            "observação_casa": "👀",
            "observação_fora": "👀",
            "neutro": "⚖️",
        }.get(snapshot.get("live_signal"), "⚖️")

        if ai_text:
            text = (
                f"{signal_emoji} {snapshot['league']} | {checkpoint}'\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x {snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"{ai_text}"
            )
        else:
            text = (
                f"{signal_emoji} {snapshot['league']} | {checkpoint}'\n"
                f"{snapshot['home_team']} {snapshot['home_score']} x {snapshot['away_score']} {snapshot['away_team']}\n\n"
                f"Sinal atual: {snapshot.get('live_signal', 'neutro')}.\n"
                f"{snapshot.get('signal_reason', 'Sem leitura forte no momento.')}"
            )

        result = self.telegram.send_message(text)
        print(f"[LIVE] Atualização {checkpoint}' enviada: {result}")

    def monitor_live_matches(self):
        if not self.football_api.is_available():
            print("[LIVE] Football API não configurada. Monitor live ignorado.")
            return

        fixtures = self.football_api.get_live_fixtures()
        monitored = [fixture for fixture in fixtures if self._is_monitored_league(fixture)]

        print(f"[LIVE] Jogos ao vivo encontrados: {len(fixtures)} | monitorados: {len(monitored)}")

        for fixture in monitored:
            try:
                fixture_id = fixture.get("fixture", {}).get("id")
                if not fixture_id:
                    continue

                events = self.football_api.get_fixture_events(int(fixture_id))
                statistics = self.football_api.get_fixture_statistics(int(fixture_id))
                stats_map = self._normalize_statistics(fixture, statistics)
                snapshot = self._build_snapshot(fixture, events, stats_map)

                previous = self.state_service.get_fixture_state(str(fixture_id)) or {}
                sent_checkpoints = previous.get("sent_checkpoints", [])
                snapshot["sent_checkpoints"] = sent_checkpoints

                previous_score = previous.get("score_signature")
                current_score = snapshot.get("score_signature")

                if previous and previous_score != current_score and snapshot.get("goal_signature"):
                    previous_goal_signature = previous.get("goal_signature")
                    if previous_goal_signature != snapshot.get("goal_signature"):
                        self._send_goal_alert(snapshot)

                checkpoint = self._checkpoint_to_send(snapshot["minute"], sent_checkpoints)
                if checkpoint is not None:
                    self._send_checkpoint_alert(snapshot, checkpoint)
                    snapshot["sent_checkpoints"] = sorted(set(sent_checkpoints + [checkpoint]))

                self.state_service.update_fixture_state(str(fixture_id), snapshot)

            except Exception as e:
                print(f"[LIVE] Erro no monitoramento do fixture {fixture.get('fixture', {}).get('id')}: {e}")