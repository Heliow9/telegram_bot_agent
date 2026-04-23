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

    home_win_rate = safe_float(home_general_form.get("win_rate"))
    away_win_rate = safe_float(away_general_form.get("win_rate"))
    home_loss_rate = safe_float(home_general_form.get("loss_rate"))
    away_loss_rate = safe_float(away_general_form.get("loss_rate"))

    home_home_draw_rate = safe_float(home_home_form.get("draw_rate"))
    away_away_draw_rate = safe_float(away_away_form.get("draw_rate"))
    home_home_win_rate = safe_float(home_home_form.get("win_rate"))
    away_away_win_rate = safe_float(away_away_form.get("win_rate"))
    home_home_loss_rate = safe_float(home_home_form.get("loss_rate"))
    away_away_loss_rate = safe_float(away_away_form.get("loss_rate"))

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

    avg_draw_rate = (home_draw_rate + away_draw_rate) / 2
    venue_avg_draw_rate = (home_home_draw_rate + away_away_draw_rate) / 2

    avg_goals_for = (home_avg_goals_for + away_avg_goals_for) / 2
    avg_goals_against = (home_avg_goals_against + away_avg_goals_against) / 2
    total_goal_environment = avg_goals_for + avg_goals_against

    absolute_rank_gap = abs((home_rank or 0) - (away_rank or 0)) if home_rank and away_rank else 0
    strength_gap = abs(home_rank_strength - away_rank_strength)
    form_gap = abs(home_form_score - away_form_score)
    venue_form_gap = abs(home_home_form_score - away_away_form_score)
    win_rate_gap = abs(home_win_rate - away_win_rate)
    draw_rate_balance = 1.0 - abs(home_draw_rate - away_draw_rate)

    low_scoring_indicator = 1.0 if total_goal_environment <= 2.4 else 0.0
    high_draw_profile_indicator = 1.0 if avg_draw_rate >= 0.28 else 0.0
    balanced_match_indicator = 1.0 if form_gap <= 0.12 and strength_gap <= 0.18 else 0.0

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

        # novas features já existentes
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

        # novas features para empate / dupla hipótese
        "home_win_rate": home_win_rate,
        "away_win_rate": away_win_rate,
        "home_loss_rate": home_loss_rate,
        "away_loss_rate": away_loss_rate,
        "home_home_draw_rate": home_home_draw_rate,
        "away_away_draw_rate": away_away_draw_rate,
        "home_home_win_rate": home_home_win_rate,
        "away_away_win_rate": away_away_win_rate,
        "home_home_loss_rate": home_home_loss_rate,
        "away_away_loss_rate": away_away_loss_rate,
        "avg_draw_rate": avg_draw_rate,
        "venue_avg_draw_rate": venue_avg_draw_rate,
        "avg_goals_for_both": avg_goals_for,
        "avg_goals_against_both": avg_goals_against,
        "total_goal_environment": total_goal_environment,
        "absolute_rank_gap": absolute_rank_gap,
        "strength_gap": strength_gap,
        "form_gap_abs": form_gap,
        "venue_form_gap_abs": venue_form_gap,
        "win_rate_gap_abs": win_rate_gap,
        "draw_rate_balance": draw_rate_balance,
        "low_scoring_indicator": low_scoring_indicator,
        "high_draw_profile_indicator": high_draw_profile_indicator,
        "balanced_match_indicator": balanced_match_indicator,
    }