import time
import threading
import requests
from typing import Dict, Any, Optional, List, Tuple
from app.config import settings


class SportsDBAPI:
    _cache_lock = threading.Lock()
    _request_lock = threading.Lock()
    _cache: Dict[Tuple[str, tuple], Tuple[float, Dict[str, Any]]] = {}
    _next_allowed_request_ts: float = 0.0

    def __init__(self):
        self.base_url = settings.sportsdb_base_url.rstrip("/")
        self.api_key = settings.sportsdb_api_key

        self.default_cache_ttl_seconds = 120
        self.event_details_cache_ttl_seconds = 15
        self.table_cache_ttl_seconds = 600
        self.team_form_cache_ttl_seconds = 300

        self.min_interval_between_requests_seconds = 1.2
        self.cooldown_on_429_seconds = 20.0

    def _build_cache_key(self, endpoint: str, params: Optional[dict]) -> Tuple[str, tuple]:
        if not params:
            return endpoint, tuple()
        normalized = tuple(sorted((str(k), str(v)) for k, v in params.items()))
        return endpoint, normalized

    def _get_cached(self, endpoint: str, params: Optional[dict]) -> Optional[Dict[str, Any]]:
        cache_key = self._build_cache_key(endpoint, params)

        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if not cached:
                return None

            expires_at, data = cached
            if time.time() > expires_at:
                del self._cache[cache_key]
                return None

            return data

    def _set_cache(self, endpoint: str, params: Optional[dict], data: Dict[str, Any], ttl: int):
        cache_key = self._build_cache_key(endpoint, params)
        with self._cache_lock:
            self._cache[cache_key] = (time.time() + ttl, data)

    def _pick_cache_ttl(self, endpoint: str) -> int:
        endpoint = endpoint.lower()

        if endpoint == "lookupevent.php":
            return self.event_details_cache_ttl_seconds

        if endpoint == "lookuptable.php":
            return self.table_cache_ttl_seconds

        if endpoint in ("eventslast.php", "eventsnext.php"):
            return self.team_form_cache_ttl_seconds

        return self.default_cache_ttl_seconds

    def _respect_global_rate_limit(self):
        with self._request_lock:
            now = time.time()

            if now < SportsDBAPI._next_allowed_request_ts:
                sleep_time = SportsDBAPI._next_allowed_request_ts - now
                time.sleep(sleep_time)

            SportsDBAPI._next_allowed_request_ts = (
                time.time() + self.min_interval_between_requests_seconds
            )

    def _register_429_cooldown(self):
        with self._request_lock:
            SportsDBAPI._next_allowed_request_ts = max(
                SportsDBAPI._next_allowed_request_ts,
                time.time() + self.cooldown_on_429_seconds,
            )

    def _error_payload(self, endpoint: str, details: str) -> Dict[str, Any]:
        return {
            "error": True,
            "message": f"Falha ao consultar {endpoint}",
            "details": details,
            "events": [],
            "results": [],
            "event": [],
            "table": [],
        }

    def _safe_int(self, value) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_status(self, status: Optional[str]) -> str:
        return str(status or "").strip().lower()

    def _is_finished_status(self, status: Optional[str]) -> bool:
        normalized = self._normalize_status(status)

        if not normalized:
            return False

        exact_statuses = {
            "ft",
            "aet",
            "pen",
            "full time",
            "match finished",
            "after extra time",
            "after penalties",
            "finished",
        }

        return normalized in exact_statuses

    def _build_result_from_scores(
        self,
        home_score: Optional[int],
        away_score: Optional[int],
    ) -> Optional[str]:
        if home_score is None or away_score is None:
            return None

        if home_score > away_score:
            return "1"
        if home_score < away_score:
            return "2"
        return "X"

    def _get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        retries: int = 2,
        retry_delay: float = 2.0,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{self.api_key}/{endpoint.lstrip('/')}"
        last_error = None

        if use_cache:
            cached = self._get_cached(endpoint, params)
            if cached is not None:
                return cached

        for attempt in range(1, retries + 1):
            response = None

            try:
                self._respect_global_rate_limit()

                response = requests.get(url, params=params or {}, timeout=30)

                if response.status_code == 429:
                    body_preview = response.text[:300]
                    last_error = f"429 Too Many Requests | body={body_preview}"
                    self._register_429_cooldown()

                    if attempt < retries:
                        time.sleep(retry_delay * attempt)
                        continue

                    print(f"[SportsDBAPI] ERRO endpoint={endpoint} params={params} details={last_error}")
                    return self._error_payload(endpoint, last_error)

                if response.status_code in (500, 502, 503, 504):
                    body_preview = response.text[:300]
                    last_error = f"{response.status_code} {response.reason} | body={body_preview}"

                    if attempt < retries:
                        time.sleep(retry_delay * attempt)
                        continue

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError:
                    body_preview = response.text[:300]
                    error_data = {
                        "error": True,
                        "message": f"Resposta inválida em {endpoint}",
                        "details": body_preview,
                        "events": [],
                        "results": [],
                        "event": [],
                        "table": [],
                    }
                    if use_cache:
                        self._set_cache(endpoint, params, error_data, 30)
                    return error_data

                if not isinstance(data, dict):
                    wrapped = {"raw": data}
                    if use_cache:
                        self._set_cache(endpoint, params, wrapped, self._pick_cache_ttl(endpoint))
                    return wrapped

                if use_cache:
                    self._set_cache(endpoint, params, data, self._pick_cache_ttl(endpoint))

                return data

            except requests.exceptions.RequestException as exc:
                body_preview = ""
                if response is not None:
                    try:
                        body_preview = response.text[:300]
                    except Exception:
                        body_preview = ""

                last_error = f"{exc} | body={body_preview}"

                if attempt < retries:
                    time.sleep(retry_delay * attempt)
                    continue

        print(f"[SportsDBAPI] ERRO endpoint={endpoint} params={params} details={last_error}")
        return self._error_payload(endpoint, last_error or "erro desconhecido")

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

    def events_by_season(self, league_id: str, season: str) -> Dict[str, Any]:
        return self._get(
            "eventsseason.php",
            {
                "id": league_id,
                "s": season,
            },
        )

    def event_by_id(self, event_id: str) -> Dict[str, Any]:
        return self._get(
            "lookupevent.php",
            {
                "id": event_id,
            },
        )

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

    def lookup_table(self, league_id: str, season: str) -> Dict[str, Any]:
        return self._get(
            "lookuptable.php",
            {
                "l": league_id,
                "s": season,
            },
        )

    def get_events_by_day_list(self, date_str: str, league_name: str) -> List[Dict[str, Any]]:
        data = self.events_by_day(date_str, league_name)
        return self.get_events_list(data)

    def get_next_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        data = self.next_events_by_league_id(league_id)
        return self.get_events_list(data)

    def get_last_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        data = self.last_events_by_league_id(league_id)
        return self.get_events_list(data)

    def get_events_by_season_list(self, league_id: str, season: str) -> List[Dict[str, Any]]:
        data = self.events_by_season(league_id, season)
        return self.get_events_list(data)

    def get_team_last_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        data = self.team_last_events(team_id)
        return self.get_events_list(data)

    def get_team_next_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        data = self.team_next_events(team_id)
        return self.get_events_list(data)

    def get_event_details(self, event_id: str) -> Optional[Dict[str, Any]]:
        data = self.event_by_id(event_id)

        if not data or data.get("error"):
            print(f"[SportsDBAPI] get_event_details sem dados para event_id={event_id} | payload={data}")
            return None

        event = self.get_first_event(data)

        if not event:
            print(f"[SportsDBAPI] get_event_details evento não encontrado para event_id={event_id} | payload={data}")
            return None

        return event

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

    def get_event_result(self, event_id: str) -> Optional[Dict[str, Any]]:
        event = self.get_event_details(event_id)
        if not event:
            return None

        raw_status = event.get("strStatus")
        status_text = (raw_status or "").strip()
        home_score = self._safe_int(event.get("intHomeScore"))
        away_score = self._safe_int(event.get("intAwayScore"))

        # CORREÇÃO CRÍTICA:
        # só considera finalizado se o status for explicitamente final
        finished = self._is_finished_status(raw_status)

        result = self._build_result_from_scores(home_score, away_score) if finished else None

        return {
            "fixture_id": str(event_id),
            "finished": finished,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "status_text": status_text.upper(),
        }