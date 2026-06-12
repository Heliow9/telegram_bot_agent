from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.services.sportsdb_api import SportsDBAPI
from app.services.time_utils import event_payload_to_local_datetime


class BasketballAnalysisService:
    """Análise simples e auditável para basquete.

    MVP operacional:
    - mercado vencedor: casa/fora;
    - mercado total de pontos: over/under em linha projetada;
    - sem ML inicialmente, porque o modelo atual foi treinado para futebol 1X2.
    """

    DEFAULT_TOTAL_LINE = 220.5

    def __init__(self):
        self.api = SportsDBAPI()
        self._team_events_cache: Dict[Tuple[str, int], List[Dict]] = {}

    def _safe_int(self, value, default: Optional[int] = None) -> Optional[int]:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_team_events(self, team_id: str, limit: int = 10) -> List[Dict]:
        team_id = str(team_id or "").strip()
        if not team_id:
            return []
        cache_key = (team_id, int(limit))
        if cache_key in self._team_events_cache:
            return self._team_events_cache[cache_key]
        events = self.api.get_team_last_events_list_limited(team_id, limit=limit) or []
        self._team_events_cache[cache_key] = events
        return events

    def _extract_form(self, events: List[Dict], team_name: str) -> Dict:
        wins = 0
        losses = 0
        points_for = 0
        points_against = 0
        totals: List[int] = []

        for event in events or []:
            home = str(event.get("strHomeTeam") or "").strip()
            away = str(event.get("strAwayTeam") or "").strip()
            home_score = self._safe_int(event.get("intHomeScore"))
            away_score = self._safe_int(event.get("intAwayScore"))
            if home_score is None or away_score is None:
                continue

            if team_name == home:
                pf, pa = home_score, away_score
            elif team_name == away:
                pf, pa = away_score, home_score
            else:
                continue

            points_for += pf
            points_against += pa
            totals.append(home_score + away_score)
            if pf > pa:
                wins += 1
            else:
                losses += 1

        games = wins + losses
        avg_for = points_for / games if games else 0.0
        avg_against = points_against / games if games else 0.0
        avg_total = sum(totals) / len(totals) if totals else 0.0

        return {
            "games": games,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / games if games else 0.0,
            "avg_points_for": avg_for,
            "avg_points_against": avg_against,
            "avg_total_points": avg_total,
            "point_diff_avg": avg_for - avg_against,
            "sample_size": games,
        }

    def _normalize_two_way(self, home_score: float, away_score: float) -> Tuple[float, float]:
        total = home_score + away_score
        if total <= 0:
            return 0.52, 0.48
        home_prob = home_score / total
        away_prob = away_score / total
        # evita probabilidade extrema em amostra curta
        home_prob = max(0.38, min(0.72, home_prob))
        away_prob = max(0.28, min(0.62, away_prob))
        total = home_prob + away_prob
        return home_prob / total, away_prob / total

    def _winner_probabilities(self, home_form: Dict, away_form: Dict) -> Tuple[float, float]:
        home_strength = (
            0.46
            + self._safe_float(home_form.get("win_rate")) * 0.24
            + self._safe_float(home_form.get("point_diff_avg")) / 55.0
            + 0.045  # fator mando em basquete
        )
        away_strength = (
            0.46
            + self._safe_float(away_form.get("win_rate")) * 0.24
            + self._safe_float(away_form.get("point_diff_avg")) / 55.0
        )
        return self._normalize_two_way(home_strength, away_strength)

    def _total_points_projection(self, home_form: Dict, away_form: Dict) -> Tuple[float, str, float]:
        home_expected = (
            self._safe_float(home_form.get("avg_points_for"), 105.0)
            + self._safe_float(away_form.get("avg_points_against"), 105.0)
        ) / 2
        away_expected = (
            self._safe_float(away_form.get("avg_points_for"), 105.0)
            + self._safe_float(home_form.get("avg_points_against"), 105.0)
        ) / 2
        projected_total = home_expected + away_expected

        if projected_total <= 0:
            projected_total = self.DEFAULT_TOTAL_LINE

        # linha sugerida arredondada para .5 para ficar com cara de mercado.
        line = round(projected_total * 2) / 2
        if line <= 120:
            line = self.DEFAULT_TOTAL_LINE

        avg_total_context = (
            self._safe_float(home_form.get("avg_total_points"), projected_total)
            + self._safe_float(away_form.get("avg_total_points"), projected_total)
        ) / 2
        signal_total = (projected_total * 0.65) + (avg_total_context * 0.35)
        pick = "OVER" if signal_total >= line else "UNDER"
        diff = abs(signal_total - line)
        probability = min(0.68, 0.52 + diff / 80.0)
        return line, pick, probability

    def _confidence(self, winner_probability: float, total_probability: float, home_form: Dict, away_form: Dict) -> str:
        min_sample = min(
            int(home_form.get("sample_size") or 0),
            int(away_form.get("sample_size") or 0),
        )
        score = 0
        if winner_probability >= 0.61:
            score += 2
        elif winner_probability >= 0.56:
            score += 1
        if total_probability >= 0.60:
            score += 1
        if min_sample >= 8:
            score += 2
        elif min_sample >= 5:
            score += 1
        if score >= 4:
            return "alta"
        if score >= 2:
            return "média"
        return "baixa"

    def build_match_analysis(self, match: Dict, league_meta: Dict) -> Optional[Dict]:
        home_team = match.get("strHomeTeam")
        away_team = match.get("strAwayTeam")
        if not home_team or not away_team:
            return None

        home_id = str(match.get("idHomeTeam") or "").strip()
        away_id = str(match.get("idAwayTeam") or "").strip()
        home_events = self._get_team_events(home_id, 12) if home_id else []
        away_events = self._get_team_events(away_id, 12) if away_id else []

        home_form = self._extract_form(home_events, home_team)
        away_form = self._extract_form(away_events, away_team)

        prob_home, prob_away = self._winner_probabilities(home_form, away_form)
        winner_pick = "1" if prob_home >= prob_away else "2"
        winner_probability = max(prob_home, prob_away)
        total_line, total_pick, total_probability = self._total_points_projection(home_form, away_form)
        confidence = self._confidence(winner_probability, total_probability, home_form, away_form)

        ranking_score = (
            winner_probability * 70
            + total_probability * 25
            + (8 if confidence == "alta" else 4 if confidence == "média" else 0)
            - int(league_meta.get("priority") or 3)
        )

        kickoff_local = event_payload_to_local_datetime(match)
        local_date = kickoff_local.strftime("%Y-%m-%d") if kickoff_local else (match.get("dateEventLocal") or match.get("dateEvent") or "")
        local_time = kickoff_local.strftime("%H:%M:%S") if kickoff_local else (match.get("strTimeLocal") or match.get("strTime") or "")

        features = {
            "sport": "basketball",
            "home_form": home_form,
            "away_form": away_form,
            "winner_probability": round(winner_probability, 4),
            "total_points_line": total_line,
            "total_points_pick": total_pick,
            "total_points_probability": round(total_probability, 4),
        }

        analysis = {
            "sport": "basketball",
            "market_type": "winner",
            "market_label": "Vencedor da partida",
            "suggested_pick": winner_pick,
            "main_market_pick": winner_pick,
            "main_market_probability": winner_probability,
            "best_probability": winner_probability,
            "prob_home": prob_home,
            "prob_draw": 0.0,
            "prob_away": prob_away,
            "confidence": confidence,
            "model_source": "basket_heuristic",
            "ml_weight": 0.0,
            "total_points_line": total_line,
            "total_points_pick": total_pick,
            "total_points_probability": total_probability,
            "total_points_label": f"{'Mais' if total_pick == 'OVER' else 'Menos'} de {total_line:.1f} pontos",
            "ranking_score": round(ranking_score, 2),
            "features": features,
            "signal_score": {
                "score": round(min(1.0, ranking_score / 100.0), 4),
                "grade": "A" if ranking_score >= 72 else "B" if ranking_score >= 64 else "C",
            },
            "value_bet": {
                "has_value": False,
                "edge": None,
                "market_odds": None,
                "fair_odds": round(1 / winner_probability, 2) if winner_probability > 0 else None,
            },
        }

        return {
            "league": league_meta,
            "fixture": {
                "sport": "basketball",
                "league": match.get("strLeague", league_meta["display_name"]),
                "league_key": league_meta["key"],
                "home_team": home_team,
                "away_team": away_team,
                "date": match.get("dateEvent", ""),
                "time": match.get("strTime", ""),
                "local_date": local_date,
                "local_time": local_time,
                "kickoff_local": kickoff_local.isoformat() if kickoff_local else None,
                "id": str(match.get("idEvent") or "").strip(),
            },
            "analysis": analysis,
        }

    def build_many_analyses(self, matches: List[Dict], league_meta: Dict) -> List[Dict]:
        payloads: List[Dict] = []
        self._team_events_cache.clear()
        for match in matches or []:
            try:
                payload = self.build_match_analysis(match, league_meta)
                if payload:
                    payloads.append(payload)
            except Exception as exc:
                print(f"[BASKET] Erro analisando jogo {match.get('idEvent')}: {exc}")
        return payloads

    def sort_by_best_picks(self, payloads: List[Dict]) -> List[Dict]:
        return sorted(
            payloads or [],
            key=lambda p: (
                p.get("analysis", {}).get("ranking_score", 0.0),
                p.get("analysis", {}).get("best_probability", 0.0),
                p.get("analysis", {}).get("total_points_probability", 0.0),
            ),
            reverse=True,
        )
