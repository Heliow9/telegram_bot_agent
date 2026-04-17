from typing import Dict, List, Optional


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_team_form(last_events: List[dict], team_name: str) -> Dict:
    wins = 0
    draws = 0
    losses = 0
    goals_for = 0
    goals_against = 0

    weighted_points = 0.0
    weighted_max_points = 0.0

    total_events = len(last_events)

    for index, event in enumerate(last_events):
        weight = max(total_events - index, 1)

        home_team = event.get("strHomeTeam")
        away_team = event.get("strAwayTeam")
        home_score = _safe_int(event.get("intHomeScore"), default=-999)
        away_score = _safe_int(event.get("intAwayScore"), default=-999)

        if home_score == -999 or away_score == -999:
            continue

        if team_name == home_team:
            gf = home_score
            ga = away_score
        elif team_name == away_team:
            gf = away_score
            ga = home_score
        else:
            continue

        goals_for += gf
        goals_against += ga

        if gf > ga:
            wins += 1
            points = 3
        elif gf == ga:
            draws += 1
            points = 1
        else:
            losses += 1
            points = 0

        weighted_points += points * weight
        weighted_max_points += 3 * weight

    games = wins + draws + losses

    avg_goals_for = goals_for / games if games else 0.0
    avg_goals_against = goals_against / games if games else 0.0
    draw_rate = draws / games if games else 0.0
    win_rate = wins / games if games else 0.0
    loss_rate = losses / games if games else 0.0
    goal_diff_total = goals_for - goals_against
    goal_diff_avg = avg_goals_for - avg_goals_against

    return {
        "games": games,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_goals_for": avg_goals_for,
        "avg_goals_against": avg_goals_against,
        "goal_diff_total": goal_diff_total,
        "goal_diff_avg": goal_diff_avg,
        "form_score": weighted_points / weighted_max_points if weighted_max_points else 0.0,
        "sample_size": games,
        "draw_rate": draw_rate,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
    }


def get_table_position(table_rows: List[dict], team_name: str) -> Optional[int]:
    for row in table_rows:
        if row.get("strTeam") == team_name:
            return _safe_int(row.get("intRank"), default=0) or None
    return None


def table_strength(rank: Optional[int], total_teams: int) -> float:
    if not rank or total_teams <= 1:
        return 0.0
    return (total_teams - rank) / (total_teams - 1)


def _combine_forms(general_form: Dict, venue_form: Dict) -> Dict:
    general_sample = _safe_int(general_form.get("sample_size"), 0)
    venue_sample = _safe_int(venue_form.get("sample_size"), 0)

    if venue_sample >= 5:
        venue_weight = 0.60
    elif venue_sample >= 3:
        venue_weight = 0.45
    elif venue_sample >= 1:
        venue_weight = 0.25
    else:
        venue_weight = 0.0

    general_weight = 1.0 - venue_weight

    return {
        "games": general_form.get("games", 0),
        "sample_size": general_sample,
        "venue_sample_size": venue_sample,
        "avg_goals_for": (
            _safe_float(general_form.get("avg_goals_for")) * general_weight
            + _safe_float(venue_form.get("avg_goals_for")) * venue_weight
        ),
        "avg_goals_against": (
            _safe_float(general_form.get("avg_goals_against")) * general_weight
            + _safe_float(venue_form.get("avg_goals_against")) * venue_weight
        ),
        "form_score": (
            _safe_float(general_form.get("form_score")) * general_weight
            + _safe_float(venue_form.get("form_score")) * venue_weight
        ),
        "draw_rate": (
            _safe_float(general_form.get("draw_rate")) * general_weight
            + _safe_float(venue_form.get("draw_rate")) * venue_weight
        ),
        "win_rate": (
            _safe_float(general_form.get("win_rate")) * general_weight
            + _safe_float(venue_form.get("win_rate")) * venue_weight
        ),
        "loss_rate": (
            _safe_float(general_form.get("loss_rate")) * general_weight
            + _safe_float(venue_form.get("loss_rate")) * venue_weight
        ),
        "goal_diff_avg": (
            _safe_float(general_form.get("goal_diff_avg")) * general_weight
            + _safe_float(venue_form.get("goal_diff_avg")) * venue_weight
        ),
        "wins": general_form.get("wins", 0),
        "draws": general_form.get("draws", 0),
        "losses": general_form.get("losses", 0),
    }


def calculate_prediction(
    home_team: str,
    away_team: str,
    home_general_form: Dict,
    away_general_form: Dict,
    home_home_form: Dict,
    away_away_form: Dict,
    home_rank: Optional[int] = None,
    away_rank: Optional[int] = None,
    total_teams: int = 20,
    league_priority: int = 99,
) -> Dict:
    home_form = _combine_forms(home_general_form, home_home_form)
    away_form = _combine_forms(away_general_form, away_away_form)

    home_table = table_strength(home_rank, total_teams)
    away_table = table_strength(away_rank, total_teams)

    home_attack_vs_away_def = (
        _safe_float(home_form["avg_goals_for"]) - _safe_float(away_form["avg_goals_against"])
    )
    away_attack_vs_home_def = (
        _safe_float(away_form["avg_goals_for"]) - _safe_float(home_form["avg_goals_against"])
    )

    home_strength = (
        _safe_float(home_form["form_score"]) * 0.28
        + _safe_float(home_form["goal_diff_avg"]) * 0.20
        + home_attack_vs_away_def * 0.14
        + home_table * 0.15
        + _safe_float(home_form["win_rate"]) * 0.10
        - _safe_float(home_form["loss_rate"]) * 0.05
        + 0.12
    )

    away_strength = (
        _safe_float(away_form["form_score"]) * 0.28
        + _safe_float(away_form["goal_diff_avg"]) * 0.20
        + away_attack_vs_home_def * 0.14
        + away_table * 0.15
        + _safe_float(away_form["win_rate"]) * 0.10
        - _safe_float(away_form["loss_rate"]) * 0.05
    )

    diff = home_strength - away_strength

    avg_draw_profile = (
        _safe_float(home_form.get("draw_rate", 0.0))
        + _safe_float(away_form.get("draw_rate", 0.0))
    ) / 2

    avg_goal_profile = (
        _safe_float(home_form["avg_goals_for"])
        + _safe_float(away_form["avg_goals_for"])
    ) / 2

    draw_boost = 0.0

    if abs(diff) < 0.10:
        draw_boost += 0.08
    elif abs(diff) < 0.18:
        draw_boost += 0.05
    elif abs(diff) < 0.26:
        draw_boost += 0.02

    if avg_draw_profile >= 0.32:
        draw_boost += 0.04
    elif avg_draw_profile >= 0.26:
        draw_boost += 0.02

    if avg_goal_profile <= 1.10:
        draw_boost += 0.04
    elif avg_goal_profile <= 1.35:
        draw_boost += 0.02

    if diff > 0.62:
        prob_home, prob_draw, prob_away = 0.64, 0.21, 0.15
    elif diff > 0.38:
        prob_home, prob_draw, prob_away = 0.56, 0.25, 0.19
    elif diff > 0.18:
        prob_home, prob_draw, prob_away = 0.47, 0.29, 0.24
    elif diff < -0.62:
        prob_home, prob_draw, prob_away = 0.15, 0.21, 0.64
    elif diff < -0.38:
        prob_home, prob_draw, prob_away = 0.19, 0.25, 0.56
    elif diff < -0.18:
        prob_home, prob_draw, prob_away = 0.24, 0.29, 0.47
    else:
        prob_home, prob_draw, prob_away = 0.35, 0.31, 0.34

    prob_draw += draw_boost

    total = prob_home + prob_draw + prob_away
    prob_home /= total
    prob_draw /= total
    prob_away /= total

    options = {
        "1": prob_home,
        "X": prob_draw,
        "2": prob_away,
    }
    suggested_pick = max(options, key=options.get)
    best_probability = options[suggested_pick]

    min_sample = min(
        _safe_int(home_general_form.get("sample_size", 0)),
        _safe_int(away_general_form.get("sample_size", 0)),
    )

    confidence_score = 0

    if best_probability >= 0.60:
        confidence_score += 2
    elif best_probability >= 0.53:
        confidence_score += 1

    if min_sample >= 7:
        confidence_score += 2
    elif min_sample >= 5:
        confidence_score += 1

    if abs(diff) >= 0.35:
        confidence_score += 1

    if confidence_score >= 4:
        confidence = "alta"
    elif confidence_score >= 2:
        confidence = "média"
    else:
        confidence = "baixa"

    score_for_ranking = (
        best_probability * 100
        + (8 if confidence == "alta" else 4 if confidence == "média" else 0)
        - league_priority
    )

    return {
        "home_team": home_team,
        "away_team": away_team,
        "prob_home": prob_home,
        "prob_draw": prob_draw,
        "prob_away": prob_away,
        "suggested_pick": suggested_pick,
        "confidence": confidence,
        "best_probability": best_probability,
        "ranking_score": round(score_for_ranking, 2),
        "home_rank": home_rank,
        "away_rank": away_rank,
        "home_form": home_form,
        "away_form": away_form,
        "home_general_form": home_general_form,
        "away_general_form": away_general_form,
        "home_home_form": home_home_form,
        "away_away_form": away_away_form,
        "debug": {
            "diff": round(diff, 4),
            "min_sample": min_sample,
            "confidence_score": confidence_score,
            "draw_boost": round(draw_boost, 4),
            "best_probability": round(best_probability, 4),
            "home_strength": round(home_strength, 4),
            "away_strength": round(away_strength, 4),
        },
    }