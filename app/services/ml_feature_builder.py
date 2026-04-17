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

    def safe_float(value, default=0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def safe_int(value, default=0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def rank_strength(rank: Optional[int]) -> float:
        if not rank or total_teams <= 1:
            return 0.0
        return (total_teams - rank) / (total_teams - 1)

    home_form_score = safe_float(home_general_form.get("form_score"))
    away_form_score = safe_float(away_general_form.get("form_score"))
    home_home_form_score = safe_float(home_home_form.get("form_score"))
    away_away_form_score = safe_float(away_away_form.get("form_score"))

    home_avg_goals_for = safe_float(home_general_form.get("avg_goals_for"))
    away_avg_goals_for = safe_float(away_general_form.get("avg_goals_for"))
    home_avg_goals_against = safe_float(home_general_form.get("avg_goals_against"))
    away_avg_goals_against = safe_float(away_general_form.get("avg_goals_against"))

    home_draw_rate = safe_float(home_general_form.get("draw_rate"))
    away_draw_rate = safe_float(away_general_form.get("draw_rate"))

    home_rank_strength = rank_strength(home_rank)
    away_rank_strength = rank_strength(away_rank)

    sample_home = safe_int(home_general_form.get("sample_size"))
    sample_away = safe_int(away_general_form.get("sample_size"))
    venue_sample_home = safe_int(home_home_form.get("sample_size"))
    venue_sample_away = safe_int(away_away_form.get("sample_size"))

    home_goal_diff = home_avg_goals_for - home_avg_goals_against
    away_goal_diff = away_avg_goals_for - away_avg_goals_against

    home_attack_vs_away_def = home_avg_goals_for - away_avg_goals_against
    away_attack_vs_home_def = away_avg_goals_for - home_avg_goals_against

    return {
        # base original
        "home_form_score": home_form_score,
        "away_form_score": away_form_score,
        "home_home_form_score": home_home_form_score,
        "away_away_form_score": away_away_form_score,
        "home_avg_goals_for": home_avg_goals_for,
        "away_avg_goals_for": away_avg_goals_for,
        "home_avg_goals_against": home_avg_goals_against,
        "away_avg_goals_against": away_avg_goals_against,
        "home_draw_rate": home_draw_rate,
        "away_draw_rate": away_draw_rate,
        "home_rank_strength": home_rank_strength,
        "away_rank_strength": away_rank_strength,
        "rank_diff": home_rank_strength - away_rank_strength,
        "league_priority": safe_int(league_priority),
        "sample_home": sample_home,
        "sample_away": sample_away,

        # novas features
        "form_diff": home_form_score - away_form_score,
        "venue_form_diff": home_home_form_score - away_away_form_score,
        "goal_diff_home": home_goal_diff,
        "goal_diff_away": away_goal_diff,
        "goal_diff_diff": home_goal_diff - away_goal_diff,
        "attack_defense_diff": home_attack_vs_away_def - away_attack_vs_home_def,
        "goals_for_diff": home_avg_goals_for - away_avg_goals_for,
        "goals_against_diff": away_avg_goals_against - home_avg_goals_against,
        "draw_rate_diff": home_draw_rate - away_draw_rate,
        "home_venue_advantage": home_home_form_score - home_form_score,
        "away_venue_advantage": away_away_form_score - away_form_score,
        "venue_advantage_diff": (
            (home_home_form_score - home_form_score)
            - (away_away_form_score - away_form_score)
        ),
        "sample_gap": sample_home - sample_away,
        "venue_sample_home": venue_sample_home,
        "venue_sample_away": venue_sample_away,
    }