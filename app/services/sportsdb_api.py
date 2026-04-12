import time
import requests
from typing import Dict, Any, Optional, List
from app.config import settings


class SportsDBAPI:
    def __init__(self):
        self.base_url = settings.sportsdb_base_url.rstrip("/")
        self.api_key = settings.sportsdb_api_key

    def _get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        retries: int = 3,
        retry_delay: float = 1.5,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{self.api_key}/{endpoint.lstrip('/')}"

        last_error = None

        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, params=params or {}, timeout=30)

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"{response.status_code} {response.reason}"
                    if attempt < retries:
                        time.sleep(retry_delay * attempt)
                        continue

                response.raise_for_status()

                data = response.json()
                if not isinstance(data, dict):
                    return {"raw": data}

                return data

            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                if attempt < retries:
                    time.sleep(retry_delay * attempt)
                    continue

        return {
            "error": True,
            "message": f"Falha ao consultar {endpoint}",
            "details": last_error,
            "events": [],
            "results": [],
            "event": [],
            "table": [],
        }

    # =============================
    # HELPERS
    # =============================
    def get_events_list(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not data or data.get("error"):
            return []

        if isinstance(data.get("events"), list):
            return data["events"]

        if isinstance(data.get("results"), list):
            return data["results"]

        if isinstance(data.get("event"), list):
            return data["event"]

        return []

    def get_first_event(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        events = self.get_events_list(data)
        return events[0] if events else None

    # =============================
    # LEAGUES
    # =============================
    def all_leagues(self) -> Dict[str, Any]:
        return self._get("all_leagues.php")

    def search_all_leagues(
        self,
        sport: str = "Soccer",
        country: str = "Brazil",
    ) -> Dict[str, Any]:
        return self._get(
            "search_all_leagues.php",
            {
                "s": sport,
                "c": country,
            },
        )

    # =============================
    # EVENTS / FIXTURES
    # =============================
    def events_by_day(self, date_str: str, league_name: str) -> Dict[str, Any]:
        return self._get(
            "eventsday.php",
            {
                "d": date_str,
                "l": league_name,
            },
        )

    def next_events_by_league_id(self, league_id: str) -> Dict[str, Any]:
        return self._get(
            "eventsnextleague.php",
            {
                "id": league_id,
            },
        )

    def last_events_by_league_id(self, league_id: str) -> Dict[str, Any]:
        return self._get(
            "eventspastleague.php",
            {
                "id": league_id,
            },
        )

    def event_by_id(self, event_id: str) -> Dict[str, Any]:
        return self._get(
            "lookupevent.php",
            {
                "id": event_id,
            },
        )

    # =============================
    # TEAM EVENTS
    # =============================
    def team_last_events(self, team_id: str) -> Dict[str, Any]:
        return self._get(
            "eventslast.php",
            {
                "id": team_id,
            },
        )

    def team_next_events(self, team_id: str) -> Dict[str, Any]:
        return self._get(
            "eventsnext.php",
            {
                "id": team_id,
            },
        )

    # =============================
    # TABLE / STANDINGS
    # =============================
    def lookup_table(self, league_id: str, season: str) -> Dict[str, Any]:
        return self._get(
            "lookuptable.php",
            {
                "l": league_id,
                "s": season,
            },
        )

    # =============================
    # READY-TO-USE METHODS
    # =============================
    def get_events_by_day_list(self, date_str: str, league_name: str) -> List[Dict[str, Any]]:
        data = self.events_by_day(date_str, league_name)
        return self.get_events_list(data)

    def get_next_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        data = self.next_events_by_league_id(league_id)
        return self.get_events_list(data)

    def get_last_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        data = self.last_events_by_league_id(league_id)
        return self.get_events_list(data)

    def get_team_last_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        data = self.team_last_events(team_id)
        return self.get_events_list(data)

    def get_team_next_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        data = self.team_next_events(team_id)
        return self.get_events_list(data)

    def get_event_details(self, event_id: str) -> Optional[Dict[str, Any]]:
        data = self.event_by_id(event_id)
        return self.get_first_event(data)

    # =============================
    # IMPROVED ANALYSIS METHODS
    # =============================
    def get_team_last_events_list_limited(self, team_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        events = self.get_team_last_events_list(team_id)
        return events[:limit]

    def get_team_last_home_events(self, team_name: str, team_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        events = self.get_team_last_events_list(team_id)
        filtered = [event for event in events if event.get("strHomeTeam") == team_name]
        return filtered[:limit]

    def get_team_last_away_events(self, team_name: str, team_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        events = self.get_team_last_events_list(team_id)
        filtered = [event for event in events if event.get("strAwayTeam") == team_name]
        return filtered[:limit]