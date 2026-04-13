from typing import Optional, Dict
from app.config import settings


class OddsService:
    def __init__(self):
        self.api_key = settings.odds_api_key

    def get_match_odds(
        self,
        home_team: str,
        away_team: str,
        league_name: str,
        match_date: str,
    ) -> Optional[Dict]:
        """
        Estrutura pronta para integrar odds reais depois.
        Retorno esperado:
        {
            "home_odds": 2.10,
            "draw_odds": 3.20,
            "away_odds": 3.60,
        }
        """
        return None