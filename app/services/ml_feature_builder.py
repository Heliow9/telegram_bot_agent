from typing import Dict, Optional


def build_match_features(
    home_general_form: Dict,
    away_general_form: Dict,
    home_home_form: Dict,
    away_away_form: Dict,
    home_rank: Optional[int],
    away_rank: Optional[int],
    total_teams: int,
    league_priority: int,
) -> Dict:
    total_teams = total_teams or 20

    def rank_strength(rank: Optional[int]) -> float:
        if not rank or total_teams <= 1:
            return 0.0
        return (total_teams - rank) / (total_teams - 1)

    return {
        "home_form_score": home_general_form.get("form_score", 0.0),
        "away_form_score": away_general_form.get("form_score", 0.0),
        "home_home_form_score": home_home_form.get("form_score", 0.0),
        "away_away_form_score": away_away_form.get("form_score", 0.0),
        "home_avg_goals_for": home_general_form.get("avg_goals_for", 0.0),
        "away_avg_goals_for": away_general_form.get("avg_goals_for", 0.0),
        "home_avg_goals_against": home_general_form.get("avg_goals_against", 0.0),
        "away_avg_goals_against": away_general_form.get("avg_goals_against", 0.0),
        "home_draw_rate": home_general_form.get("draw_rate", 0.0),
        "away_draw_rate": away_general_form.get("draw_rate", 0.0),
        "home_rank_strength": rank_strength(home_rank),
        "away_rank_strength": rank_strength(away_rank),
        "rank_diff": rank_strength(home_rank) - rank_strength(away_rank),
        "league_priority": league_priority,
        "sample_home": home_general_form.get("sample_size", 0),
        "sample_away": away_general_form.get("sample_size", 0),
    }