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


def _normalize_probabilities(prob_home: float, prob_draw: float, prob_away: float):
    total = prob_home + prob_draw + prob_away
    if total <= 0:
        return 0.3333, 0.3333, 0.3334

    return (
        prob_home / total,
        prob_draw / total,
        prob_away / total,
    )


def _build_double_chance(prob_home: float, prob_draw: float, prob_away: float) -> Dict[str, float]:
    dc_1x = prob_home + prob_draw
    dc_x2 = prob_draw + prob_away
    dc_12 = prob_home + prob_away

    return {
        "1X": dc_1x,
        "X2": dc_x2,
        "12": dc_12,
    }


def _pick_best_main_market(prob_home: float, prob_draw: float, prob_away: float):
    options = {
        "1": prob_home,
        "X": prob_draw,
        "2": prob_away,
    }
    pick = max(options, key=options.get)
    return pick, options[pick], options


def _pick_best_double_chance(prob_home: float, prob_draw: float, prob_away: float):
    options = _build_double_chance(prob_home, prob_draw, prob_away)
    pick = max(options, key=options.get)
    return pick, options[pick], options


def _decide_best_market(
    prob_home: float,
    prob_draw: float,
    prob_away: float,
    confidence: str,
):
    main_pick, main_prob, main_options = _pick_best_main_market(
        prob_home, prob_draw, prob_away
    )
    dc_pick, dc_prob, dc_options = _pick_best_double_chance(
        prob_home, prob_draw, prob_away
    )

    # Regras para começar:
    # - se o 1x2 estiver forte, mantém 1x2
    # - se o jogo estiver equilibrado, permite dupla hipótese
    # - se o empate estiver muito presente, favorece 1X ou X2
    draw_prob = prob_draw
    strength_gap = abs(prob_home - prob_away)

    preferred_market_type = "1x2"
    suggested_pick = main_pick
    best_probability = main_prob

    if main_prob < 0.50 and dc_prob >= 0.72:
        preferred_market_type = "double_chance"
        suggested_pick = dc_pick
        best_probability = dc_prob

    if draw_prob >= 0.30 and dc_prob >= 0.70:
        preferred_market_type = "double_chance"
        suggested_pick = dc_pick
        best_probability = dc_prob

    if strength_gap <= 0.10 and dc_prob >= 0.68:
        preferred_market_type = "double_chance"
        suggested_pick = dc_pick
        best_probability = dc_prob

    if confidence == "alta" and main_prob >= 0.54:
        preferred_market_type = "1x2"
        suggested_pick = main_pick
        best_probability = main_prob

    return {
        "market_type": preferred_market_type,
        "suggested_pick": suggested_pick,
        "best_probability": best_probability,
        "main_market_pick": main_pick,
        "main_market_probability": main_prob,
        "double_chance_pick": dc_pick,
        "double_chance_probability": dc_prob,
        "main_market_probs": main_options,
        "double_chance_probs": dc_options,
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

    if abs(diff) < 0.08:
        draw_boost += 0.09
    elif abs(diff) < 0.16:
        draw_boost += 0.06
    elif abs(diff) < 0.24:
        draw_boost += 0.03

    if avg_draw_profile >= 0.32:
        draw_boost += 0.045
    elif avg_draw_profile >= 0.27:
        draw_boost += 0.025

    if avg_goal_profile <= 1.10:
        draw_boost += 0.04
    elif avg_goal_profile <= 1.35:
        draw_boost += 0.02

    low_sample_flag = min(
        _safe_int(home_general_form.get("sample_size", 0)),
        _safe_int(away_general_form.get("sample_size", 0)),
    ) < 4
    if low_sample_flag and abs(diff) < 0.20:
        draw_boost += 0.02

    if diff > 0.70:
        prob_home, prob_draw, prob_away = 0.63, 0.21, 0.16
    elif diff > 0.42:
        prob_home, prob_draw, prob_away = 0.55, 0.25, 0.20
    elif diff > 0.20:
        prob_home, prob_draw, prob_away = 0.46, 0.29, 0.25
    elif diff < -0.70:
        prob_home, prob_draw, prob_away = 0.16, 0.21, 0.63
    elif diff < -0.42:
        prob_home, prob_draw, prob_away = 0.20, 0.25, 0.55
    elif diff < -0.20:
        prob_home, prob_draw, prob_away = 0.25, 0.29, 0.46
    else:
        prob_home, prob_draw, prob_away = 0.35, 0.31, 0.34

    prob_draw += draw_boost

    # Em jogos muito equilibrados e com alta tendência de empate, reduz extremos.
    if avg_draw_profile >= 0.30 and abs(diff) < 0.22:
        prob_home *= 0.97
        prob_away *= 0.97
        prob_draw *= 1.06

    prob_home, prob_draw, prob_away = _normalize_probabilities(
        prob_home,
        prob_draw,
        prob_away,
    )

    main_pick, main_best_probability, main_options = _pick_best_main_market(
        prob_home,
        prob_draw,
        prob_away,
    )

    min_sample = min(
        _safe_int(home_general_form.get("sample_size", 0)),
        _safe_int(away_general_form.get("sample_size", 0)),
    )

    confidence_score = 0

    if main_best_probability >= 0.60:
        confidence_score += 2
    elif main_best_probability >= 0.53:
        confidence_score += 1

    if min_sample >= 7:
        confidence_score += 2
    elif min_sample >= 5:
        confidence_score += 1

    if abs(diff) >= 0.35:
        confidence_score += 1

    if low_sample_flag and abs(diff) < 0.28 and main_pick in {"1", "2"} and main_best_probability < 0.55:
        confidence_score = max(confidence_score - 1, 0)

    if confidence_score >= 4:
        confidence = "alta"
    elif confidence_score >= 2:
        confidence = "média"
    else:
        confidence = "baixa"

    market_decision = _decide_best_market(
        prob_home=prob_home,
        prob_draw=prob_draw,
        prob_away=prob_away,
        confidence=confidence,
    )

    score_for_ranking = (
        market_decision["best_probability"] * 100
        + (8 if confidence == "alta" else 4 if confidence == "média" else 0)
        - league_priority
    )

    return {
        "home_team": home_team,
        "away_team": away_team,

        # probabilidades 1x2
        "prob_home": prob_home,
        "prob_draw": prob_draw,
        "prob_away": prob_away,

        # probabilidades dupla hipótese
        "prob_1x": round(prob_home + prob_draw, 4),
        "prob_x2": round(prob_draw + prob_away, 4),
        "prob_12": round(prob_home + prob_away, 4),

        # decisão principal
        "market_type": market_decision["market_type"],
        "suggested_pick": market_decision["suggested_pick"],
        "confidence": confidence,
        "best_probability": market_decision["best_probability"],
        "ranking_score": round(score_for_ranking, 2),

        # apoio para auditoria
        "main_market_pick": market_decision["main_market_pick"],
        "main_market_probability": market_decision["main_market_probability"],
        "double_chance_pick": market_decision["double_chance_pick"],
        "double_chance_probability": market_decision["double_chance_probability"],

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
            "best_probability": round(market_decision["best_probability"], 4),
            "home_strength": round(home_strength, 4),
            "away_strength": round(away_strength, 4),
            "market_type": market_decision["market_type"],
            "main_market_probs": {
                "1": round(main_options["1"], 4),
                "X": round(main_options["X"], 4),
                "2": round(main_options["2"], 4),
            },
            "double_chance_probs": {
                "1X": round(prob_home + prob_draw, 4),
                "X2": round(prob_draw + prob_away, 4),
                "12": round(prob_home + prob_away, 4),
            },
        },
    }