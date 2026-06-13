from app.services.cache_service import CacheService
from app.services.daily_leagues_service import DailyLeaguesService
from app.services.sportsdb_api import SportsDBAPI


class FakeResponse:
    status_code = 200
    reason = "OK"
    headers = {}
    text = "ok"

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


def reset_cache():
    CacheService._client = None
    CacheService._memory.clear()


def tune(api: SportsDBAPI):
    api.max_requests_per_minute = 100
    api.min_interval_seconds = 0.01
    api.rate_limit_max_wait_seconds = 1


def test_identical_requests_share_cache():
    reset_cache()
    api = SportsDBAPI()
    tune(api)
    calls = []
    api.session.get = lambda *args, **kwargs: (
        calls.append(1) or FakeResponse({"events": [{"idEvent": "x"}]})
    )

    first = api.events_by_day_sport("2099-01-01", "Basketball")
    second = api.events_by_day_sport("2099-01-01", "Basketball")

    assert first == second
    assert len(calls) == 1


def test_429_opens_shared_cooldown():
    reset_cache()
    api = SportsDBAPI()
    tune(api)
    api.cooldown_on_429_seconds = 60
    calls = []

    class Response429:
        status_code = 429
        reason = "Too Many Requests"
        headers = {"Retry-After": "60"}
        text = "limited"

        def json(self):
            return {}

        def raise_for_status(self):
            return None

    api.session.get = lambda *args, **kwargs: calls.append(1) or Response429()

    first = api.events_by_day_sport("2099-01-02", "Basketball")
    second = api.events_by_day_sport("2099-01-03", "Basketball")

    assert first["rate_limited"] is True
    assert second["rate_limited"] is True
    assert len(calls) == 1


def test_three_basketball_leagues_use_one_eventsday_call():
    reset_cache()
    service = DailyLeaguesService()
    tune(service.api)
    calls = []
    events = [
        {"idEvent": "nba1", "idLeague": "4387", "strLeague": "NBA", "strHomeTeam": "A", "strAwayTeam": "B", "dateEvent": "2099-01-04", "strTime": "20:00:00", "strStatus": "NS"},
        {"idEvent": "g1", "idLeague": "4388", "strLeague": "NBA G League", "strHomeTeam": "C", "strAwayTeam": "D", "dateEvent": "2099-01-04", "strTime": "21:00:00", "strStatus": "NS"},
        {"idEvent": "n1", "idLeague": "4607", "strLeague": "NCAA Division I Basketball Mens", "strHomeTeam": "E", "strAwayTeam": "F", "dateEvent": "2099-01-04", "strTime": "22:00:00", "strStatus": "NS"},
    ]
    service.api.session.get = lambda *args, **kwargs: (
        calls.append(1) or FakeResponse({"events": events})
    )

    payloads = service.get_basketball_all_day_payloads("2099-01-04")

    assert len(payloads) == 3
    assert len(calls) == 1
