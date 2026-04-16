import unicodedata
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

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
        value = value.replace(".", " ")
        value = value.replace("/", " ")
        value = value.replace("&", " ")
        value = value.replace("fc", " ")
        value = value.replace("cf", " ")
        value = value.replace("club", " ")
        value = value.replace("associazione", " ")
        value = value.replace("sportiva", " ")
        value = value.replace("de", " ")
        value = value.replace("da", " ")
        value = value.replace("do", " ")
        value = value.replace("del", " ")
        value = " ".join(value.split())
        return value.strip()

    def _normalize_league_name(self, league_name: str) -> str:
        return self._normalize_text(league_name)

    # ---------------------------------------------------------------------
    # MAPEAMENTO DE LIGAS
    # ---------------------------------------------------------------------
    def _find_sport_key(self, league_name: str) -> Optional[str]:
        normalized = self._normalize_league_name(league_name)

        mapping = {
            # já usadas
            "premier league": "soccer_epl",
            "brasileirao serie a": "soccer_brazil_campeonato",
            "argentina liga profesional": "soccer_argentina_primera_division",
            "italia serie a": "soccer_italy_serie_a",
            "turquia super lig": "soccer_turkey_super_league",
            "liga dos campeoes": "soccer_uefa_champs_league",
            "championship": "soccer_efl_champ",

            # novas cobertas
            "liga europa": "soccer_uefa_europa_league",
            "uefa europa league": "soccer_uefa_europa_league",
            "europa league": "soccer_uefa_europa_league",

            "libertadores": "soccer_conmebol_copa_libertadores",
            "copa libertadores": "soccer_conmebol_copa_libertadores",
            "conmebol copa libertadores": "soccer_conmebol_copa_libertadores",

            "copa sul americana": "soccer_conmebol_copa_sudamericana",
            "copa sudamericana": "soccer_conmebol_copa_sudamericana",
            "sudamericana": "soccer_conmebol_copa_sudamericana",
            "conmebol copa sudamericana": "soccer_conmebol_copa_sudamericana",
        }

        return mapping.get(normalized)

    # ---------------------------------------------------------------------
    # ALIASES DE TIMES
    # ---------------------------------------------------------------------
    def _team_aliases(self, team_name: str) -> List[str]:
        raw = str(team_name or "").strip()
        normalized = self._normalize_text(raw)

        aliases = {raw.lower().strip(), normalized}

        custom_aliases = {
            "atletico mineiro": ["atletico mg", "atletico-mg", "atletico mineiro"],
            "palmeiras": ["palmeiras"],
            "sporting cristal": ["sporting cristal"],
            "corinthians": ["corinthians"],
            "lanus": ["lanus"],
            "always ready": ["always ready"],
            "real betis": ["real betis", "betis"],
            "braga": ["braga", "sporting braga"],
            "aston villa": ["aston villa"],
            "bologna": ["bologna"],
            "nottingham forest": ["nottingham forest"],
            "fc porto": ["porto", "fc porto"],
            "celta vigo": ["celta vigo", "celta de vigo"],
            "freiburg": ["freiburg", "sc freiburg"],
            "river plate": ["river plate"],
            "carabobo": ["carabobo"],
            "tigre": ["tigre"],
            "macara": ["macara"],
            "america cali": ["america de cali", "america cali"],
            "alianza atletico": ["alianza atletico"],
            "independiente del valle": ["independiente del valle"],
            "universidad central": ["universidad central"],
            "fluminense": ["fluminense"],
            "independiente rivadavia": ["independiente rivadavia"],
        }

        if normalized in custom_aliases:
            for alias in custom_aliases[normalized]:
                aliases.add(self._normalize_text(alias))
                aliases.add(alias.lower().strip())

        return [alias for alias in aliases if alias]

    # ---------------------------------------------------------------------
    # MATCH DE TIMES
    # ---------------------------------------------------------------------
    def _team_names_match(self, api_name: str, target_name: str) -> bool:
        a = self._normalize_text(api_name)
        b_aliases = self._team_aliases(target_name)

        if not a:
            return False

        if a in b_aliases:
            return True

        for b in b_aliases:
            if not b:
                continue

            if a == b:
                return True

            if a in b or b in a:
                return True

            a_tokens = set(a.split())
            b_tokens = set(b.split())

            if not a_tokens or not b_tokens:
                continue

            overlap = len(a_tokens.intersection(b_tokens))
            min_required = 2 if min(len(a_tokens), len(b_tokens)) >= 2 else 1

            if overlap >= min_required:
                return True

        return False

    def _match_game(self, game: Dict[str, Any], home_team: str, away_team: str) -> bool:
        return (
            self._team_names_match(game.get("home_team", ""), home_team)
            and self._team_names_match(game.get("away_team", ""), away_team)
        )

    # ---------------------------------------------------------------------
    # DATA
    # ---------------------------------------------------------------------
    def _same_match_date(self, commence_time: Optional[str], match_date: str) -> bool:
        if not commence_time or not match_date:
            return True

        try:
            raw = commence_time.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%Y-%m-%d") == str(match_date).strip()
        except Exception:
            return True

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

                if home_odds is not None and away_odds is not None:
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
            print("[ODDS] Serviço indisponível: api_key ausente.")
            return None

        sport_key = self._find_sport_key(league_name)

        if sport_key is None:
            print(f"[ODDS] Liga sem cobertura mapeada internamente: {league_name}")
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

            if response.status_code == 404:
                print(
                    f"[ODDS] Liga não disponível na API para a chave "
                    f"{sport_key}: {league_name}"
                )
                return None

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                print(f"[ODDS] Payload inesperado para {league_name}: {type(data)}")
                return None

            candidates: List[Dict[str, Any]] = []

            for game in data:
                if not self._same_match_date(game.get("commence_time"), match_date):
                    continue

                if self._match_game(game, home_team, away_team):
                    candidates.append(game)

            if not candidates:
                print(
                    f"[ODDS] Jogo não encontrado na liga {league_name} "
                    f"({sport_key}): {home_team} x {away_team} | data={match_date}"
                )
                return None

            for game in candidates:
                odds = self._extract_h2h_odds(game, home_team, away_team)
                if odds:
                    print(
                        f"[ODDS] Odds encontradas | {league_name} | "
                        f"{home_team} x {away_team} | bookmaker={odds.get('bookmaker')}"
                    )
                    return odds

            print(
                f"[ODDS] Odds não encontradas nos bookmakers | "
                f"{league_name} | {home_team} x {away_team}"
            )
            return None

        except Exception as e:
            print(
                f"[ODDS] Erro ao buscar odds | "
                f"liga={league_name} | jogo={home_team} x {away_team} | erro={e}"
            )
            return None