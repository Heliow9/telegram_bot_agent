import requests
from typing import Optional, Dict, Any, List
from app.config import settings


class FootballAPI:
    def __init__(self):
        self.base_url = settings.football_api_base_url.rstrip("/")
        self.api_key = settings.football_api_key
        self.headers = {
            "x-apisports-key": self.api_key,
        }

    # =============================
    # CORE REQUEST
    # =============================
    def _get(self, endpoint: str, params: Optional[dict] = None) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "warning": "FOOTBALL_API_KEY não configurada",
                "response": [],
                "errors": ["missing_api_key"],
            }

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = requests.get(
            url,
            headers=self.headers,
            params=params or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    # =============================
    # LEAGUES
    # =============================
    def get_leagues(
        self,
        league_id: Optional[int] = None,
        country: Optional[str] = None,
        season: Optional[int] = None,
        current: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params = {}

        if league_id is not None:
            params["id"] = league_id
        if country is not None:
            params["country"] = country
        if season is not None:
            params["season"] = season
        if current is not None:
            params["current"] = "true" if current else "false"

        return self._get("leagues", params)

    def get_current_season_by_league(self, league_id: int) -> Optional[int]:
        data = self.get_leagues(league_id=league_id, current=True)
        leagues = data.get("response", [])

        if not leagues:
            return None

        seasons = leagues[0].get("seasons", [])
        for season in seasons:
            if season.get("current") is True:
                return season.get("year")

        return None

    # =============================
    # FIXTURES
    # =============================
    def get_fixtures_by_date(
        self,
        date_str: str,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {"date": date_str}

        if league_id is not None:
            params["league"] = league_id
        if season is not None:
            params["season"] = season
        if timezone is not None:
            params["timezone"] = timezone

        return self._get("fixtures", params)

    def get_fixtures_by_date_auto_season(
        self,
        date_str: str,
        league_id: int,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        season = self.get_current_season_by_league(league_id)

        if season is None:
            return {
                "warning": f"Não foi possível descobrir a season da liga {league_id}",
                "response": [],
                "errors": ["season_not_found"],
            }

        return self.get_fixtures_by_date(
            date_str=date_str,
            league_id=league_id,
            season=season,
            timezone=timezone,
        )

    def get_fixtures_by_leagues_auto_season(
        self,
        date_str: str,
        league_ids: List[int],
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        all_games = []

        for league_id in league_ids:
            data = self.get_fixtures_by_date_auto_season(
                date_str=date_str,
                league_id=league_id,
                timezone=timezone,
            )
            all_games.extend(data.get("response", []))

        return {"response": all_games}

    def get_next_fixtures_by_league(
        self,
        league_id: int,
        season: int,
        next_matches: int = 10,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "league": league_id,
            "season": season,
            "next": next_matches,
        }

        if timezone is not None:
            params["timezone"] = timezone

        return self._get("fixtures", params)

    def get_all_fixtures_by_league_season(
        self,
        league_id: int,
        season: int,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "league": league_id,
            "season": season,
        }

        if timezone is not None:
            params["timezone"] = timezone

        return self._get("fixtures", params)

    def get_next_fixtures_by_league_fallback(
        self,
        league_id: int,
        season: int,
        next_matches: int = 10,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = self.get_all_fixtures_by_league_season(
            league_id=league_id,
            season=season,
            timezone=timezone,
        )

        fixtures = data.get("response", [])

        upcoming = []
        for item in fixtures:
            status = (
                item.get("fixture", {})
                .get("status", {})
                .get("short")
            )

            # NS = Not Started
            if status == "NS":
                upcoming.append(item)

        # ordena por data
        upcoming.sort(
            key=lambda x: x.get("fixture", {}).get("timestamp", 0)
        )

        return {
            "response": upcoming[:next_matches],
            "source": "fallback_full_season_filter",
            "total_season_fixtures": len(fixtures),
            "total_upcoming_found": len(upcoming),
        }

    def get_last_matches_by_team(
        self,
        team_id: int,
        last: int = 5,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "team": team_id,
            "last": last,
        }

        if timezone is not None:
            params["timezone"] = timezone

        return self._get("fixtures", params)

    def get_team_statistics(
        self,
        league_id: int,
        season: int,
        team_id: int,
    ) -> Dict[str, Any]:
        params = {
            "league": league_id,
            "season": season,
            "team": team_id,
        }

        return self._get("teams/statistics", params)

    # =============================
    # DEBUG HELPERS
    # =============================
    def debug_next_fixtures_by_league(
        self,
        league_id: int,
        season: int,
        next_matches: int = 5,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = self.get_next_fixtures_by_league(
            league_id=league_id,
            season=season,
            next_matches=next_matches,
            timezone=timezone,
        )

        return {
            "parameters": data.get("parameters"),
            "errors": data.get("errors"),
            "results": data.get("results"),
            "paging": data.get("paging"),
            "response_count": len(data.get("response", [])),
            "response_preview": data.get("response", [])[:2],
        }