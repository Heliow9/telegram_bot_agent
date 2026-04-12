from typing import Dict, List, Optional


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
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

    return {
        "games": games,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_goals_for": goals_for / games if games else 0.0,
        "avg_goals_against": goals_against / games if games else 0.0,
        "form_score": weighted_points / weighted_max_points if weighted_max_points else 0.0,
        "sample_size": games,
        "draw_rate": draws / games if games else 0.0,
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
    venue_weight = 0.60 if venue_form.get("sample_size", 0) >= 3 else 0.35

    return {
        "games": general_form.get("games", 0),
        "sample_size": general_form.get("sample_size", 0),
        "venue_sample_size": venue_form.get("sample_size", 0),
        "avg_goals_for": (
            general_form.get("avg_goals_for", 0.0) * (1 - venue_weight)
            + venue_form.get("avg_goals_for", 0.0) * venue_weight
        ),
        "avg_goals_against": (
            general_form.get("avg_goals_against", 0.0) * (1 - venue_weight)
            + venue_form.get("avg_goals_against", 0.0) * venue_weight
        ),
        "form_score": (
            general_form.get("form_score", 0.0) * (1 - venue_weight)
            + venue_form.get("form_score", 0.0) * venue_weight
        ),
        "draw_rate": (
            general_form.get("draw_rate", 0.0) * (1 - venue_weight)
            + venue_form.get("draw_rate", 0.0) * venue_weight
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

    home_strength = (
        home_form["form_score"] * 0.34 +
        home_form["avg_goals_for"] * 0.18 -
        home_form["avg_goals_against"] * 0.12 +
        home_table * 0.16 +
        0.18
    )

    away_strength = (
        away_form["form_score"] * 0.34 +
        away_form["avg_goals_for"] * 0.18 -
        away_form["avg_goals_against"] * 0.12 +
        away_table * 0.16
    )

    diff = home_strength - away_strength

    avg_draw_profile = (home_form.get("draw_rate", 0.0) + away_form.get("draw_rate", 0.0)) / 2
    avg_goal_profile = (home_form["avg_goals_for"] + away_form["avg_goals_for"]) / 2

    draw_boost = 0.0

    if abs(diff) < 0.12:
        draw_boost += 0.07
    elif abs(diff) < 0.22:
        draw_boost += 0.03

    if avg_draw_profile > 0.30:
        draw_boost += 0.04

    if avg_goal_profile < 1.15:
        draw_boost += 0.03

    if diff > 0.55:
        prob_home, prob_draw, prob_away = 0.62, 0.22, 0.16
    elif diff > 0.30:
        prob_home, prob_draw, prob_away = 0.54, 0.26, 0.20
    elif diff > 0.12:
        prob_home, prob_draw, prob_away = 0.46, 0.29, 0.25
    elif diff < -0.55:
        prob_home, prob_draw, prob_away = 0.16, 0.22, 0.62
    elif diff < -0.30:
        prob_home, prob_draw, prob_away = 0.20, 0.26, 0.54
    elif diff < -0.12:
        prob_home, prob_draw, prob_away = 0.25, 0.29, 0.46
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
        home_general_form.get("sample_size", 0),
        away_general_form.get("sample_size", 0),
    )

    confidence_score = 0

    if best_probability >= 0.58:
        confidence_score += 2
    elif best_probability >= 0.50:
        confidence_score += 1

    if min_sample >= 5:
        confidence_score += 2
    elif min_sample >= 3:
        confidence_score += 1

    if abs(diff) >= 0.30:
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
        },
    }