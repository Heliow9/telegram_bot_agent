import time
import requests
from typing import Dict, Any, Optional, List

from app.config import settings


class FootballAPIService:
    def __init__(self):
        self.base_url = settings.football_api_base_url.rstrip("/")
        self.api_key = settings.football_api_key

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-apisports-key": self.api_key,
        }

    def _get(
        self,
        path: str,
        params: Optional[dict] = None,
        retries: int = 3,
        retry_delay: float = 1.5,
    ) -> Dict[str, Any]:
        if not self.is_available():
            return {
                "error": True,
                "message": "Football API não configurada",
                "response": [],
            }

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error = None

        for attempt in range(1, retries + 1):
            response = None
            try:
                response = requests.get(
                    url,
                    headers=self._headers(),
                    params=params or {},
                    timeout=30,
                )

                if response.status_code in (429, 500, 502, 503, 504):
                    body_preview = response.text[:300]
                    last_error = f"{response.status_code} {response.reason} | body={body_preview}"
                    if attempt < retries:
                        time.sleep(retry_delay * attempt)
                        continue

                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {"response": []}

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

        print(f"[FOOTBALL_API] ERRO path={path} params={params} details={last_error}")
        return {
            "error": True,
            "message": f"Falha ao consultar {path}",
            "details": last_error,
            "response": [],
        }

    def get_live_fixtures(self, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"live": "all"}
        if league_id:
            params["league"] = league_id

        data = self._get("fixtures", params=params)
        response = data.get("response")
        return response if isinstance(response, list) else []

    def get_fixture_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        data = self._get("fixtures/events", params={"fixture": fixture_id})
        response = data.get("response")
        return response if isinstance(response, list) else []

    def get_fixture_statistics(self, fixture_id: int) -> List[Dict[str, Any]]:
        data = self._get("fixtures/statistics", params={"fixture": fixture_id})
        response = data.get("response")
        return response if isinstance(response, list) else []

    def get_fixture_by_id(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        data = self._get("fixtures", params={"id": fixture_id})
        response = data.get("response")
        if isinstance(response, list) and response:
            return response[0]
        return None