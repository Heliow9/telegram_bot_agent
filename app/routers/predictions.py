from fastapi import APIRouter
from app.services.sportsdb_api import SportsDBAPI

router = APIRouter(prefix="/predictions", tags=["predictions"])

api = SportsDBAPI()

LEAGUES = {
    "brasileirao": {
        "id": "4351",
        "name": "Brazilian Serie A",
        "season": "2026",
    },
    "premier_league": {
        "id": "4328",
        "name": "English Premier League",
        "season": "2025-2026",
    },
}


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/leagues")
def get_supported_leagues():
    return LEAGUES


@router.get("/next/brasileirao")
def next_brasileirao_games():
    return api.next_events_by_league_id(LEAGUES["brasileirao"]["id"])


@router.get("/next/premier")
def next_premier_games():
    return api.next_events_by_league_id(LEAGUES["premier_league"]["id"])


@router.get("/event/{event_id}")
def event_details(event_id: str):
    return api.event_by_id(event_id)