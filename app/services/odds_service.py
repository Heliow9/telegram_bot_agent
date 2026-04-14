import unicodedata
import requests
from typing import Optional, Dict, Any, List
from app.config import settings


class OddsService:
    def __init__(self):
        self.api_key = settings.odds_api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self.regions = settings.odds_regions
        self.markets = settings.odds_markets
        self.odds_format = settings.odds_format

    def is_available(self) -> bool:
        return bool(self.api_key)

    # ---------------------------------------------------------------------
    # NORMALIZAÇÃO
    # ---------------------------------------------------------------------
    def _normalize_text(self, value: str) -> str:
        if not value:
            return ""

        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = value.lower()
        value = value.replace("-", " ")
        value = value.replace(".", "")
        value = value.replace("fc", " ")
        value = value.replace("cf", " ")
        value = value.replace("club", " ")
        value = value.replace("associazione", " ")
        value = value.replace("sportiva", " ")
        value = value.replace("de", " ")
        value = value.replace("da", " ")
        value = " ".join(value.split())
        return value.strip()

    # ---------------------------------------------------------------------
    # MAPEAMENTO DE LIGAS
    # ---------------------------------------------------------------------
    def _find_sport_key(self, league_name: str) -> Optional[str]:
        normalized = self._normalize_text(league_name)

        mapping = {
            # ✅ SUPORTADAS
            "premier league": "soccer_epl",
            "brasileirao serie a": "soccer_brazil_campeonato",
            "argentina liga profesional": "soccer_argentina_primera_division",
            "italia serie a": "soccer_italy_serie_a",
            "turquia super lig": "soccer_turkey_super_league",
            "liga dos campeoes": "soccer_uefa_champs_league",
            "championship": "soccer_efl_champ",

            # ❌ NÃO SUPORTADAS (tratadas com fallback)
            "libertadores": None,
            "copa sul americana": None,
        }

        return mapping.get(normalized)

    # ---------------------------------------------------------------------
    # MATCH DE TIMES
    # ---------------------------------------------------------------------
    def _team_names_match(self, api_name: str, target_name: str) -> bool:
        a = self._normalize_text(api_name)
        b = self._normalize_text(target_name)

        if a == b:
            return True

        if a in b or b in a:
            return True

        a_tokens = set(a.split())
        b_tokens = set(b.split())

        if not a_tokens or not b_tokens:
            return False

        overlap = len(a_tokens.intersection(b_tokens))
        return overlap >= 1

    def _match_game(self, game: Dict[str, Any], home_team: str, away_team: str) -> bool:
        return (
            self._team_names_match(game.get("home_team", ""), home_team)
            and self._team_names_match(game.get("away_team", ""), away_team)
        )

    # ---------------------------------------------------------------------
    # EXTRAÇÃO DE ODDS
    # ---------------------------------------------------------------------
    def _extract_h2h_odds(
        self,
        game: Dict[str, Any],
        home_team: str,
        away_team: str,
    ) -> Optional[Dict[str, Any]]:
        bookmakers: List[Dict[str, Any]] = game.get("bookmakers", [])
        if not bookmakers:
            return None

        for bookmaker in bookmakers:
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue

                home_odds = None
                draw_odds = None
                away_odds = None

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price")

                    if price is None:
                        continue

                    if self._team_names_match(name, home_team):
                        home_odds = float(price)
                    elif self._team_names_match(name, away_team):
                        away_odds = float(price)
                    elif self._normalize_text(name) == "draw":
                        draw_odds = float(price)

                if home_odds and away_odds:
                    return {
                        "home_odds": home_odds,
                        "draw_odds": draw_odds,
                        "away_odds": away_odds,
                        "bookmaker": bookmaker.get("title"),
                    }

        return None

    # ---------------------------------------------------------------------
    # BUSCA PRINCIPAL
    # ---------------------------------------------------------------------
    def get_match_odds(
        self,
        home_team: str,
        away_team: str,
        league_name: str,
        match_date: str = "",
    ) -> Optional[Dict[str, Any]]:

        if not self.is_available():
            return None

        sport_key = self._find_sport_key(league_name)

        # 🔥 Fallback inteligente
        if sport_key is None:
            print(f"[ODDS] Liga sem cobertura: {league_name}")
            return None

        url = f"{self.base_url}/sports/{sport_key}/odds"

        params = {
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": self.markets,
            "oddsFormat": self.odds_format,
        }

        try:
            response = requests.get(url, params=params, timeout=20)

            # 🔥 evita log feio de erro
            if response.status_code == 404:
                print(f"[ODDS] Liga não disponível na API: {league_name}")
                return None

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                return None

            for game in data:
                if self._match_game(game, home_team, away_team):
                    odds = self._extract_h2h_odds(game, home_team, away_team)
                    if odds:
                        return odds

            print(f"[ODDS] Odds não encontradas: {home_team} x {away_team}")
            return None

        except Exception as e:
            print(f"[ODDS] Erro ao buscar odds: {home_team} x {away_team} | {e}")
            return None