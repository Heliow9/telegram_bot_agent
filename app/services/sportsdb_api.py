from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.config import settings
from app.services.cache_service import CacheService


class SportsDBAPI:
    """Gateway local para a TheSportsDB otimizado para o plano gratuito.

    O gateway centraliza em Redis:
    - cache fresco e cache obsoleto (stale-if-error);
    - lock por consulta para impedir chamadas duplicadas entre processos;
    - limite global por minuto compartilhado entre API, scheduler e Celery;
    - intervalo mínimo global entre requisições;
    - cooldown/circuit breaker após HTTP 429 ou falhas repetidas.

    Assim, todos os componentes usam uma única "saída" lógica para a API,
    sem proxy rotativo e sem tentar contornar limites do provedor.
    """

    _fallback_request_lock = threading.RLock()
    _fallback_next_allowed_ts = 0.0
    _fallback_cache: Dict[str, Tuple[float, Any]] = {}

    def __init__(self):
        self.base_url = settings.sportsdb_base_url.rstrip("/")
        self.api_key = settings.sportsdb_api_key
        self.cache = CacheService()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Bet2026-SportsDB-Gateway/2.0",
                "Accept": "application/json,text/plain,*/*",
                "Connection": "keep-alive",
            }
        )

        self.proxy_enabled = bool(settings.sportsdb_proxy_enabled)
        self.max_requests_per_minute = max(1, int(settings.sportsdb_max_requests_per_minute))
        self.min_interval_seconds = max(0.1, float(settings.sportsdb_min_interval_seconds))
        self.request_timeout_seconds = max(2, int(settings.sportsdb_request_timeout_seconds))
        self.rate_limit_max_wait_seconds = max(0.0, float(settings.sportsdb_rate_limit_max_wait_seconds))
        self.cooldown_on_429_seconds = max(30, int(settings.sportsdb_429_cooldown_seconds))
        self.singleflight_wait_seconds = max(0.0, float(settings.sportsdb_singleflight_wait_seconds))
        self.stale_ttl_seconds = max(3600, int(settings.sportsdb_stale_ttl_seconds))

        self.eventsday_cache_ttl_seconds = max(300, int(settings.sportsdb_eventsday_cache_ttl_seconds))
        self.nextleague_cache_ttl_seconds = max(600, int(settings.sportsdb_nextleague_cache_ttl_seconds))
        self.team_cache_ttl_seconds = max(1800, int(settings.sportsdb_team_cache_ttl_seconds))
        self.table_cache_ttl_seconds = max(1800, int(settings.sportsdb_table_cache_ttl_seconds))
        self.event_cache_ttl_seconds = max(30, int(settings.sportsdb_event_cache_ttl_seconds))

    # ------------------------------------------------------------------
    # Cache / chaves
    # ------------------------------------------------------------------
    def _canonical_params(self, params: Optional[dict]) -> dict:
        return {str(k): str(v) for k, v in sorted((params or {}).items())}

    def _request_hash(self, endpoint: str, params: Optional[dict]) -> str:
        raw = json.dumps(
            {"endpoint": endpoint.lower().lstrip("/"), "params": self._canonical_params(params)},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _fresh_key(self, endpoint: str, params: Optional[dict]) -> str:
        return f"sportsdb:response:fresh:{self._request_hash(endpoint, params)}"

    def _stale_key(self, endpoint: str, params: Optional[dict]) -> str:
        return f"sportsdb:response:stale:{self._request_hash(endpoint, params)}"

    def _fetch_lock_key(self, endpoint: str, params: Optional[dict]) -> str:
        return f"sportsdb:fetch-lock:{self._request_hash(endpoint, params)}"

    def _pick_cache_ttl(self, endpoint: str) -> int:
        endpoint = endpoint.lower().lstrip("/")
        if endpoint == "eventsday.php":
            return self.eventsday_cache_ttl_seconds
        if endpoint == "eventsnextleague.php":
            return self.nextleague_cache_ttl_seconds
        if endpoint in {"eventspastleague.php", "eventsseason.php"}:
            return self.team_cache_ttl_seconds
        if endpoint in {"eventslast.php", "eventsnext.php"}:
            return self.team_cache_ttl_seconds
        if endpoint == "lookuptable.php":
            return self.table_cache_ttl_seconds
        if endpoint == "lookupevent.php":
            return self.event_cache_ttl_seconds
        if endpoint in {"all_leagues.php", "search_all_leagues.php"}:
            return 86400
        return 900

    def _get_cached(self, endpoint: str, params: Optional[dict], *, stale: bool = False) -> Optional[Dict[str, Any]]:
        key = self._stale_key(endpoint, params) if stale else self._fresh_key(endpoint, params)
        value = self.cache.get(key)
        if isinstance(value, dict):
            return value
        return None

    def _set_cached(self, endpoint: str, params: Optional[dict], data: Dict[str, Any]) -> None:
        fresh_ttl = self._pick_cache_ttl(endpoint)
        self.cache.set(self._fresh_key(endpoint, params), data, ttl_seconds=fresh_ttl)
        self.cache.set(self._stale_key(endpoint, params), data, ttl_seconds=self.stale_ttl_seconds)

    # ------------------------------------------------------------------
    # Rate limit compartilhado / cooldown
    # ------------------------------------------------------------------
    def _minute_bucket(self, now: Optional[float] = None) -> str:
        now = now or time.time()
        return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d%H%M")

    def _cooldown_remaining(self) -> int:
        raw = self.cache.get_raw("sportsdb:cooldown-until", "0")
        try:
            until = float(raw or 0)
        except (TypeError, ValueError):
            until = 0.0
        return max(0, int(until - time.time()))

    def _set_cooldown(self, seconds: int, reason: str) -> None:
        seconds = max(30, int(seconds))
        until = time.time() + seconds
        current_raw = self.cache.get_raw("sportsdb:cooldown-until", "0")
        try:
            current = float(current_raw or 0)
        except (TypeError, ValueError):
            current = 0.0
        if until > current:
            self.cache.set_raw("sportsdb:cooldown-until", until, ttl_seconds=seconds + 60)
            self.cache.set(
                "sportsdb:cooldown-reason",
                {"reason": reason, "created_at": datetime.now(timezone.utc).isoformat(), "seconds": seconds},
                ttl_seconds=seconds + 60,
            )
        print(f"[SportsDBProxy] cooldown={seconds}s reason={reason}")

    def _parse_retry_after(self, response: requests.Response) -> int:
        raw = str(response.headers.get("Retry-After") or "").strip()
        if raw.isdigit():
            return max(self.cooldown_on_429_seconds, int(raw))
        if raw:
            try:
                target = parsedate_to_datetime(raw)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                seconds = int((target - datetime.now(timezone.utc)).total_seconds())
                return max(self.cooldown_on_429_seconds, seconds)
            except Exception:
                pass
        return self.cooldown_on_429_seconds

    def _reserve_request_slot(self) -> Tuple[bool, str]:
        """Reserva uma chamada no orçamento global gratuito.

        Não espera mais do que alguns segundos. Se o orçamento acabou, retorna
        rapidamente e o chamador usa cache stale ou tenta em execução futura.
        """
        cooldown = self._cooldown_remaining()
        if cooldown > 0:
            return False, f"cooldown:{cooldown}s"

        deadline = time.time() + self.rate_limit_max_wait_seconds
        while True:
            token = self.cache.acquire_lock("sportsdb:rate-mutex", ttl_seconds=8)
            if token:
                try:
                    now = time.time()
                    cooldown = self._cooldown_remaining()
                    if cooldown > 0:
                        return False, f"cooldown:{cooldown}s"

                    bucket = self._minute_bucket(now)
                    count_key = f"sportsdb:rate-count:{bucket}"
                    raw_count = self.cache.get_raw(count_key, "0")
                    try:
                        count = int(raw_count or 0)
                    except (TypeError, ValueError):
                        count = 0

                    raw_next = self.cache.get_raw("sportsdb:next-allowed-ts", "0")
                    try:
                        next_allowed = float(raw_next or 0)
                    except (TypeError, ValueError):
                        next_allowed = 0.0

                    if count >= self.max_requests_per_minute:
                        return False, f"minute-budget:{count}/{self.max_requests_per_minute}"

                    if now < next_allowed:
                        wait = next_allowed - now
                    else:
                        wait = 0.0

                    if wait <= 0:
                        new_count = self.cache.increment(count_key, ttl_seconds=90)
                        self.cache.set_raw(
                            "sportsdb:next-allowed-ts",
                            now + self.min_interval_seconds,
                            ttl_seconds=max(10, int(self.min_interval_seconds * 4)),
                        )
                        return True, f"slot:{new_count}/{self.max_requests_per_minute}"
                finally:
                    self.cache.release_lock("sportsdb:rate-mutex", token)

                if time.time() + wait > deadline:
                    return False, f"interval-wait:{wait:.2f}s"
                time.sleep(min(wait, 0.5))
                continue

            if time.time() >= deadline:
                return False, "rate-lock-timeout"
            time.sleep(0.08)

    # ------------------------------------------------------------------
    # Respostas / erros
    # ------------------------------------------------------------------
    def _error_payload(
        self,
        endpoint: str,
        details: str,
        *,
        rate_limited: bool = False,
        stale_available: bool = False,
    ) -> Dict[str, Any]:
        return {
            "error": True,
            "message": f"Falha ao consultar {endpoint}",
            "details": details,
            "rate_limited": rate_limited,
            "stale_available": stale_available,
            "events": [],
            "results": [],
            "event": [],
            "table": [],
        }

    def _return_stale_or_error(
        self,
        endpoint: str,
        params: Optional[dict],
        details: str,
        *,
        rate_limited: bool = False,
    ) -> Dict[str, Any]:
        stale = self._get_cached(endpoint, params, stale=True)
        if stale is not None:
            print(f"[SportsDBProxy] STALE endpoint={endpoint} params={params} reason={details}")
            return stale
        return self._error_payload(endpoint, details, rate_limited=rate_limited)

    def is_rate_limited_payload(self, data: Optional[Dict[str, Any]]) -> bool:
        return bool(isinstance(data, dict) and data.get("error") and data.get("rate_limited"))

    def status(self) -> Dict[str, Any]:
        bucket = self._minute_bucket()
        raw_count = self.cache.get_raw(f"sportsdb:rate-count:{bucket}", "0")
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            count = 0
        return {
            "proxy_enabled": self.proxy_enabled,
            "redis_connected": bool(self.cache.client),
            "shared_demo_key": str(self.api_key).strip() == "123",
            "key_warning": (
                "A chave 123 é pública/compartilhada; o gateway reduz chamadas, "
                "mas o limite também pode ser consumido por terceiros."
                if str(self.api_key).strip() == "123" else None
            ),
            "requests_this_minute": count,
            "max_requests_per_minute": self.max_requests_per_minute,
            "remaining_this_minute": max(0, self.max_requests_per_minute - count),
            "cooldown_remaining_seconds": self._cooldown_remaining(),
            "cooldown_reason": self.cache.get("sportsdb:cooldown-reason"),
            "min_interval_seconds": self.min_interval_seconds,
            "eventsday_cache_ttl_seconds": self.eventsday_cache_ttl_seconds,
            "stale_ttl_seconds": self.stale_ttl_seconds,
        }

    # ------------------------------------------------------------------
    # HTTP centralizado
    # ------------------------------------------------------------------
    def _get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        retries: int = 1,
        retry_delay: float = 1.0,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{self.api_key}/{endpoint}"

        if use_cache:
            cached = self._get_cached(endpoint, params, stale=False)
            if cached is not None:
                return cached

        cooldown = self._cooldown_remaining()
        if cooldown > 0:
            return self._return_stale_or_error(
                endpoint,
                params,
                f"cooldown global ativo por {cooldown}s",
                rate_limited=True,
            )

        # Single-flight: só um processo chama o upstream para a mesma URL.
        fetch_lock_key = self._fetch_lock_key(endpoint, params)
        fetch_token = self.cache.acquire_lock(
            fetch_lock_key,
            ttl_seconds=max(15, self.request_timeout_seconds + 8),
        )
        if not fetch_token:
            deadline = time.time() + self.singleflight_wait_seconds
            while time.time() < deadline:
                time.sleep(0.15)
                cached = self._get_cached(endpoint, params, stale=False)
                if cached is not None:
                    return cached
            return self._return_stale_or_error(
                endpoint,
                params,
                "consulta idêntica já está em processamento",
            )

        try:
            # Outra instância pode ter preenchido o cache enquanto adquiríamos lock.
            if use_cache:
                cached = self._get_cached(endpoint, params, stale=False)
                if cached is not None:
                    return cached

            allowed, rate_reason = self._reserve_request_slot()
            if not allowed:
                return self._return_stale_or_error(
                    endpoint,
                    params,
                    f"limite local preventivo: {rate_reason}",
                    rate_limited=True,
                )

            last_error = "erro desconhecido"
            attempts = max(1, min(int(retries), 2))
            for attempt in range(1, attempts + 1):
                response: Optional[requests.Response] = None
                try:
                    response = self.session.get(
                        url,
                        params=params or {},
                        timeout=self.request_timeout_seconds,
                    )

                    if response.status_code == 429:
                        retry_after = self._parse_retry_after(response)
                        body_preview = response.text[:180].replace("\n", " ")
                        last_error = f"429 Too Many Requests | retry_after={retry_after}s | body={body_preview}"
                        self._set_cooldown(retry_after, f"429:{endpoint}")
                        return self._return_stale_or_error(
                            endpoint,
                            params,
                            last_error,
                            rate_limited=True,
                        )

                    if response.status_code in {500, 502, 503, 504}:
                        body_preview = response.text[:180].replace("\n", " ")
                        last_error = f"{response.status_code} {response.reason} | body={body_preview}"
                        if attempt < attempts:
                            time.sleep(min(2.0, retry_delay * attempt))
                            continue
                        self._set_cooldown(60, f"upstream-{response.status_code}:{endpoint}")
                        return self._return_stale_or_error(endpoint, params, last_error)

                    response.raise_for_status()
                    try:
                        data = response.json()
                    except ValueError:
                        body_preview = response.text[:180].replace("\n", " ")
                        last_error = f"resposta não JSON | body={body_preview}"
                        return self._return_stale_or_error(endpoint, params, last_error)

                    if not isinstance(data, dict):
                        data = {"raw": data}

                    if use_cache:
                        self._set_cached(endpoint, params, data)
                    print(f"[SportsDBProxy] UPSTREAM endpoint={endpoint} params={params} rate={rate_reason}")
                    return data

                except requests.exceptions.RequestException as exc:
                    body_preview = ""
                    if response is not None:
                        try:
                            body_preview = response.text[:180].replace("\n", " ")
                        except Exception:
                            body_preview = ""
                    last_error = f"{type(exc).__name__}: {exc} | body={body_preview}"
                    if attempt < attempts:
                        time.sleep(min(2.0, retry_delay * attempt))
                        continue

            print(f"[SportsDBProxy] ERRO endpoint={endpoint} params={params} details={last_error}")
            return self._return_stale_or_error(endpoint, params, last_error)
        finally:
            self.cache.release_lock(fetch_lock_key, fetch_token)

    # ------------------------------------------------------------------
    # Helpers de domínio
    # ------------------------------------------------------------------
    def get_events_list(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not data or data.get("error"):
            return []
        for key in ("events", "results", "event"):
            if isinstance(data.get(key), list):
                return data[key]
        return []

    def get_first_event(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        events = self.get_events_list(data)
        return events[0] if events else None

    def all_leagues(self) -> Dict[str, Any]:
        return self._get("all_leagues.php")

    def search_all_leagues(self, sport: str = "Soccer", country: str = "Brazil") -> Dict[str, Any]:
        return self._get("search_all_leagues.php", {"s": sport, "c": country})

    def events_by_day(self, date_str: str, league_name: str) -> Dict[str, Any]:
        return self._get("eventsday.php", {"d": date_str, "l": league_name})

    def events_by_day_sport(self, date_str: str, sport: str = "Soccer") -> Dict[str, Any]:
        return self._get("eventsday.php", {"d": date_str, "s": sport})

    def next_events_by_league_id(self, league_id: str) -> Dict[str, Any]:
        return self._get("eventsnextleague.php", {"id": league_id})

    def last_events_by_league_id(self, league_id: str) -> Dict[str, Any]:
        return self._get("eventspastleague.php", {"id": league_id})

    def events_by_season(self, league_id: str, season: str) -> Dict[str, Any]:
        return self._get("eventsseason.php", {"id": league_id, "s": season})

    def event_by_id(self, event_id: str) -> Dict[str, Any]:
        return self._get("lookupevent.php", {"id": event_id})

    def team_last_events(self, team_id: str) -> Dict[str, Any]:
        return self._get("eventslast.php", {"id": team_id})

    def team_next_events(self, team_id: str) -> Dict[str, Any]:
        return self._get("eventsnext.php", {"id": team_id})

    def lookup_table(self, league_id: str, season: str) -> Dict[str, Any]:
        return self._get("lookuptable.php", {"l": league_id, "s": season})

    def get_events_by_day_list(self, date_str: str, league_name: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.events_by_day(date_str, league_name))

    def get_events_by_day_sport_list(self, date_str: str, sport: str = "Soccer") -> List[Dict[str, Any]]:
        return self.get_events_list(self.events_by_day_sport(date_str, sport=sport))

    def get_next_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.next_events_by_league_id(league_id))

    def get_last_events_by_league_list(self, league_id: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.last_events_by_league_id(league_id))

    def get_events_by_season_list(self, league_id: str, season: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.events_by_season(league_id, season))

    def get_team_last_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.team_last_events(team_id))

    def get_team_next_events_list(self, team_id: str) -> List[Dict[str, Any]]:
        return self.get_events_list(self.team_next_events(team_id))

    def get_event_details(self, event_id: str) -> Optional[Dict[str, Any]]:
        data = self.event_by_id(event_id)
        if not data or data.get("error"):
            print(f"[SportsDBProxy] get_event_details sem dados event_id={event_id} details={data.get('details') if isinstance(data, dict) else data}")
            return None
        return self.get_first_event(data)

    def get_team_last_events_list_limited(self, team_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.get_team_last_events_list(team_id)[:limit]

    def get_team_last_home_events(self, team_name: str, team_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        events = self.get_team_last_events_list(team_id)
        return [event for event in events if event.get("strHomeTeam") == team_name][:limit]

    def get_team_last_away_events(self, team_name: str, team_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        events = self.get_team_last_events_list(team_id)
        return [event for event in events if event.get("strAwayTeam") == team_name][:limit]

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
        exact = {
            "ft", "aet", "pen", "full time", "match finished", "after extra time",
            "after penalties", "finished", "final",
        }
        return normalized in exact or "finished" in normalized or normalized.startswith("final")

    def _build_result_from_scores(self, home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return "1"
        if home_score < away_score:
            return "2"
        return "X"

    def get_event_result(self, event_id: str) -> Optional[Dict[str, Any]]:
        event = self.get_event_details(event_id)
        if not event:
            return None
        raw_status = event.get("strStatus")
        status_text = str(raw_status or "").strip()
        home_score = self._safe_int(event.get("intHomeScore"))
        away_score = self._safe_int(event.get("intAwayScore"))
        finished = self._is_finished_status(raw_status)
        result = self._build_result_from_scores(home_score, away_score) if finished else None
        return {
            "fixture_id": str(event_id),
            "finished": finished,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "status_text": status_text.upper(),
            "locked": str(event.get("strLocked") or "").strip().lower(),
            "date_event": str(event.get("dateEvent") or "").strip(),
            "time_event": str(event.get("strTime") or "").strip(),
        }
