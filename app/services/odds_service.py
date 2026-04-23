import unicodedata
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import requests

from app.config import settings
from app.services.runtime_config_service import load_runtime_config


class OddsService:
    ROTATE_STATUS_CODES = {401, 403, 429}

    def __init__(self):
        self.base_url = "https://api.the-odds-api.com/v4"
        self.regions = settings.odds_regions
        self.markets = settings.odds_markets
        self.odds_format = settings.odds_format

    # ---------------------------------------------------------------------
    # CONFIG
    # ---------------------------------------------------------------------
    def _load_api_keys(self) -> List[str]:
        runtime = load_runtime_config()
        raw_keys = runtime.get("odds_api_keys", [])

        if not isinstance(raw_keys, list):
            return []

        cleaned = []
        seen = set()

        for item in raw_keys:
            key = str(item or "").strip()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(key)

        return cleaned

    def is_available(self) -> bool:
        return len(self._load_api_keys()) > 0

    def _mask_key(self, api_key: str) -> str:
        if not api_key:
            return "sem_key"
        if len(api_key) <= 8:
            return "***"
        return f"{api_key[:4]}...{api_key[-4:]}"

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
            "premier league": "soccer_epl",
            "brasileirao serie a": "soccer_brazil_campeonato",
            "argentina liga profesional": "soccer_argentina_primera_division",
            "italia serie a": "soccer_italy_serie_a",
            "turquia super lig": "soccer_turkey_super_league",
            "liga dos campeoes": "soccer_uefa_champs_league",
            "championship": "soccer_efl_champ",
            "bundesliga": "soccer_germany_bundesliga",
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
            "la liga": "soccer_spain_la_liga",
            "laliga": "soccer_spain_la_liga",
            "liga portugal": "soccer_portugal_primeira_liga",
            "primeira liga": "soccer_portugal_primeira_liga",
            "ligue 1": "soccer_france_ligue_one",
            "eredivisie": "soccer_netherlands_eredivisie",
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
            "psg": ["paris saint germain", "psg"],
            "manchester united": ["manchester united", "man utd"],
            "manchester city": ["manchester city", "man city"],
            "internazionale": ["inter", "inter milan", "internazionale"],
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
    # REQUEST
    # ---------------------------------------------------------------------
    def _request_with_key(
        self,
        api_key: str,
        sport_key: str,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[int], Optional[str]]:
        url = f"{self.base_url}/sports/{sport_key}/odds"

        params = {
            "apiKey": api_key,
            "regions": self.regions,
            "markets": self.markets,
            "oddsFormat": self.odds_format,
        }

        try:
            response = requests.get(url, params=params, timeout=20)

            if response.status_code == 404:
                return None, 404, "Liga não disponível na API"

            if response.status_code in self.ROTATE_STATUS_CODES:
                return None, response.status_code, response.text[:300]

            response.raise_for_status()

            data = response.json()
            if not isinstance(data, list):
                return None, response.status_code, f"Payload inesperado: {type(data)}"

            return data, response.status_code, None

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            body = ""
            if e.response is not None:
                try:
                    body = e.response.text[:300]
                except Exception:
                    body = ""
            return None, status_code, body or str(e)

        except Exception as e:
            return None, None, str(e)

    # ---------------------------------------------------------------------
    # EXTRAÇÃO DE ODDS
    # ---------------------------------------------------------------------
    def _extract_1x2_odds(
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
                        "bookmaker": bookmaker.get("title"),
                        "home_odds": home_odds,
                        "draw_odds": draw_odds,
                        "away_odds": away_odds,
                    }

        return None

    def _build_double_chance_odds_from_1x2(
        self,
        odds_1x2: Optional[Dict[str, Any]],
    ) -> Dict[str, Optional[float]]:
        if not odds_1x2:
            return {
                "odds_1x": None,
                "odds_x2": None,
                "odds_12": None,
            }

        home_odds = odds_1x2.get("home_odds")
        draw_odds = odds_1x2.get("draw_odds")
        away_odds = odds_1x2.get("away_odds")

        def safe_inverse(value):
            try:
                value = float(value)
                if value <= 0:
                    return None
                return 1 / value
            except Exception:
                return None

        p1 = safe_inverse(home_odds)
        px = safe_inverse(draw_odds)
        p2 = safe_inverse(away_odds)

        def combined_odds(pa, pb):
            if pa is None or pb is None:
                return None
            total = pa + pb
            if total <= 0:
                return None
            return round(1 / total, 4)

        return {
            "odds_1x": combined_odds(p1, px),
            "odds_x2": combined_odds(px, p2),
            "odds_12": combined_odds(p1, p2),
        }

    # ---------------------------------------------------------------------
    # PRINCIPAL
    # ---------------------------------------------------------------------
    def get_match_odds(
        self,
        home_team: str,
        away_team: str,
        league_name: str,
        match_date: str = "",
    ) -> Optional[Dict[str, Any]]:
        api_keys = self._load_api_keys()

        if not api_keys:
            print("[ODDS] Serviço indisponível: nenhuma odds_api_keys configurada.")
            return None

        sport_key = self._find_sport_key(league_name)

        if sport_key is None:
            print(f"[ODDS] Liga sem cobertura mapeada internamente: {league_name}")
            return None

        last_error = None

        for index, api_key in enumerate(api_keys, start=1):
            masked = self._mask_key(api_key)

            data, status_code, error = self._request_with_key(api_key, sport_key)

            if data is not None:
                candidates: List[Dict[str, Any]] = []

                for game in data:
                    if not self._same_match_date(game.get("commence_time"), match_date):
                        continue

                    if self._match_game(game, home_team, away_team):
                        candidates.append(game)

                if not candidates:
                    print(
                        f"[ODDS] Jogo não encontrado na liga {league_name} "
                        f"({sport_key}) com key #{index} [{masked}] | "
                        f"{home_team} x {away_team} | data={match_date}"
                    )
                    return None

                for game in candidates:
                    odds_1x2 = self._extract_1x2_odds(game, home_team, away_team)
                    if odds_1x2:
                        dc_odds = self._build_double_chance_odds_from_1x2(odds_1x2)

                        result = {
                            "bookmaker": odds_1x2.get("bookmaker"),
                            "home_odds": odds_1x2.get("home_odds"),
                            "draw_odds": odds_1x2.get("draw_odds"),
                            "away_odds": odds_1x2.get("away_odds"),
                            "odds_1x": dc_odds.get("odds_1x"),
                            "odds_x2": dc_odds.get("odds_x2"),
                            "odds_12": dc_odds.get("odds_12"),
                        }

                        print(
                            f"[ODDS] Odds encontradas | {league_name} | "
                            f"{home_team} x {away_team} | bookmaker={result.get('bookmaker')} | "
                            f"key #{index} [{masked}]"
                        )
                        return result

                print(
                    f"[ODDS] Odds não encontradas nos bookmakers | "
                    f"{league_name} | {home_team} x {away_team} | "
                    f"key #{index} [{masked}]"
                )
                return None

            last_error = error

            if status_code == 404:
                print(
                    f"[ODDS] Liga não disponível na API para a chave {sport_key}: "
                    f"{league_name}"
                )
                return None

            if status_code in self.ROTATE_STATUS_CODES:
                print(
                    f"[ODDS] Key bloqueada/limitada, tentando próxima | "
                    f"key #{index} [{masked}] | status={status_code}"
                )
                continue

            print(
                f"[ODDS] Erro ao buscar odds com key #{index} [{masked}] | "
                f"liga={league_name} | jogo={home_team} x {away_team} | "
                f"status={status_code} | erro={error}"
            )
            return None

        print(
            f"[ODDS] Todas as keys falharam | liga={league_name} | "
            f"jogo={home_team} x {away_team} | último_erro={last_error}"
        )
        return None