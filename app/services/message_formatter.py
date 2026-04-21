from collections import defaultdict
from app.services.time_utils import format_local_datetime


LEAGUE_EMOJIS = {
    "Brasileirão Série A": "🇧🇷",
    "Brasileirão Série B": "🇧🇷",
    "Copa do Brasil": "🇧🇷",
    "Premier League": "🏴",
    "LaLiga": "🇪🇸",
    "Liga Europa": "🇪🇺",
    "Argentina Liga Profesional": "🇦🇷",
    "Itália Série A": "🇮🇹",
    "Turquia Super Lig": "🇹🇷",
    "Liga dos Campeões": "🇪🇺",
    "Copa Sul-Americana": "🌎",
    "Libertadores": "🏆",
    "Championship": "🏴",
    "Bundesliga": "🇩🇪",
}


def _safe_text(value) -> str:
    return str(value or "").strip()


def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _escape_markdown(text: str) -> str:
    text = _safe_text(text)

    replacements = [
        ("\\", "\\\\"),
        ("_", "\\_"),
        ("*", "\\*"),
        ("[", "\\["),
        ("]", "\\]"),
        ("(", "\\("),
        (")", "\\)"),
        ("~", "\\~"),
        ("`", "\\`"),
        (">", "\\>"),
        ("#", "\\#"),
        ("+", "\\+"),
        ("-", "\\-"),
        ("=", "\\="),
        ("|", "\\|"),
        ("{", "\\{"),
        ("}", "\\}"),
        (".", "\\."),
        ("!", "\\!"),
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def _md(value) -> str:
    return _escape_markdown(_safe_text(value))


def _time_only(date_value: str, time_value: str) -> str:
    _, local_time = format_local_datetime(date_value, time_value)
    return local_time[:5] if local_time else "--:--"


def _league_emoji(league_name: str) -> str:
    return LEAGUE_EMOJIS.get(league_name, "🏆")


def _confidence_label(confidence: str) -> str:
    mapping = {
        "alta": "Alta",
        "média": "Média",
        "media": "Média",
        "baixa": "Baixa",
    }
    return mapping.get(str(confidence).lower(), str(confidence))


def _pick_label(pick: str) -> str:
    pick = str(pick or "").upper().strip()

    mapping = {
        "1": "Casa",
        "X": "Empate",
        "2": "Fora",
        "1X": "Casa ou Empate",
        "X2": "Empate ou Fora",
        "12": "Casa ou Fora",
    }
    return mapping.get(pick, pick)


def _market_type_label(market_type: str) -> str:
    market_type = str(market_type or "").lower().strip()

    mapping = {
        "1x2": "1X2",
        "double_chance": "Dupla Hipótese",
    }
    return mapping.get(market_type, market_type or "1X2")


def _result_label(real_result: str, home_team: str, away_team: str) -> str:
    real_result = str(real_result or "").upper().strip()

    if real_result == "1":
        return f"{home_team} venceu"
    if real_result == "2":
        return f"{away_team} venceu"
    if real_result == "X":
        return "Empate"
    return str(real_result)


def _resolve_market_type(analysis: dict | None = None, item: dict | None = None) -> str:
    analysis = analysis or {}
    item = item or {}

    market_type = (
        analysis.get("market_type")
        or item.get("market_type")
    )

    return str(market_type or "1x2").lower().strip()


def _resolve_final_pick(analysis: dict | None = None, item: dict | None = None) -> str:
    analysis = analysis or {}
    item = item or {}

    pick = (
        analysis.get("suggested_pick")
        or item.get("pick")
    )

    return str(pick or "").upper().strip()


def _resolve_value_bet(analysis: dict | None = None) -> dict:
    analysis = analysis or {}
    return analysis.get("value_bet") or {}


def _resolve_value_bet_details(analysis: dict | None = None) -> dict:
    value_bet = _resolve_value_bet(analysis)
    details = value_bet.get("details") or {}

    if details:
        return details

    # Compatibilidade com formato novo sem "details"
    pick = _resolve_final_pick(analysis)
    market_type = _resolve_market_type(analysis)

    return {
        "market": pick,
        "label": value_bet.get("label") or _pick_label(pick),
        "odds": value_bet.get("market_odds"),
        "fair_odds": value_bet.get("fair_odds"),
        "edge": value_bet.get("edge"),
        "market_type": value_bet.get("market_type") or market_type,
        "pick": value_bet.get("pick") or pick,
        "model_prob": analysis.get("best_probability"),
        "implied_prob": None,
    }


def _get_pick_market_odds(analysis: dict):
    odds = analysis.get("odds") or {}
    pick = _resolve_final_pick(analysis)
    market_type = _resolve_market_type(analysis)

    if market_type == "double_chance":
        if pick == "1X":
            return _safe_float(odds.get("odds_1x"))
        if pick == "X2":
            return _safe_float(odds.get("odds_x2"))
        if pick == "12":
            return _safe_float(odds.get("odds_12"))
        return None

    if pick == "1":
        return _safe_float(odds.get("home_odds"))
    if pick == "X":
        return _safe_float(odds.get("draw_odds"))
    if pick == "2":
        return _safe_float(odds.get("away_odds"))

    return None


def _get_pick_fair_odds(analysis: dict):
    fair_odds = analysis.get("fair_odds") or {}
    pick = _resolve_final_pick(analysis)
    market_type = _resolve_market_type(analysis)

    if market_type == "double_chance":
        if pick == "1X":
            return _safe_float(fair_odds.get("1X") or fair_odds.get("1x"))
        if pick == "X2":
            return _safe_float(fair_odds.get("X2") or fair_odds.get("x2"))
        if pick == "12":
            return _safe_float(fair_odds.get("12"))
        return None

    return _safe_float(fair_odds.get(pick))


def _get_pick_edge(analysis: dict):
    value_bet = _resolve_value_bet(analysis)
    details = _resolve_value_bet_details(analysis)

    direct_edge = _safe_float(value_bet.get("edge"))
    if direct_edge is not None:
        return direct_edge

    details_edge = _safe_float(details.get("edge"))
    if details_edge is not None:
        return details_edge

    return None


def _get_best_probability(analysis: dict):
    return _safe_float(analysis.get("best_probability"))


def _get_main_probabilities_text(analysis: dict) -> str:
    return (
        f"{float(analysis.get('prob_home') or 0):.0%} • "
        f"{float(analysis.get('prob_draw') or 0):.0%} • "
        f"{float(analysis.get('prob_away') or 0):.0%}"
    )


def _has_double_chance_probabilities(analysis: dict) -> bool:
    return any(
        analysis.get(key) is not None
        for key in ("prob_1x", "prob_x2", "prob_12")
    )


def _format_probabilities(analysis: dict) -> list[str]:
    lines = [
        "*Probabilidades 1X2*",
        f"• Casa: *{float(analysis.get('prob_home') or 0):.0%}*",
        f"• Empate: *{float(analysis.get('prob_draw') or 0):.0%}*",
        f"• Fora: *{float(analysis.get('prob_away') or 0):.0%}*",
    ]

    if _has_double_chance_probabilities(analysis):
        lines.extend([
            "",
            "*Probabilidades Dupla Hipótese*",
            f"• 1X: *{float(analysis.get('prob_1x') or 0):.0%}*",
            f"• X2: *{float(analysis.get('prob_x2') or 0):.0%}*",
            f"• 12: *{float(analysis.get('prob_12') or 0):.0%}*",
        ])

    return lines


def _format_odds(analysis: dict) -> list[str]:
    odds = analysis.get("odds")
    if not odds:
        return []

    lines = ["", "📉 *Odds de Mercado*"]

    if odds.get("home_odds") is not None:
        lines.append(f"• Casa: *{float(odds['home_odds']):.2f}*")
    if odds.get("draw_odds") is not None:
        lines.append(f"• Empate: *{float(odds['draw_odds']):.2f}*")
    if odds.get("away_odds") is not None:
        lines.append(f"• Fora: *{float(odds['away_odds']):.2f}*")

    if odds.get("odds_1x") is not None:
        lines.append(f"• 1X: *{float(odds['odds_1x']):.2f}*")
    if odds.get("odds_x2") is not None:
        lines.append(f"• X2: *{float(odds['odds_x2']):.2f}*")
    if odds.get("odds_12") is not None:
        lines.append(f"• 12: *{float(odds['odds_12']):.2f}*")

    if odds.get("bookmaker"):
        lines.append(f"• Bookmaker: *{_md(odds['bookmaker'])}*")

    return lines


def _format_odds_comparison(analysis: dict) -> list[str]:
    comparison = analysis.get("odds_comparison")
    if not comparison:
        return []

    fair_odds = _safe_float(comparison.get("fair_odds"))
    current_odds = _safe_float(comparison.get("current_odds"))

    if fair_odds is None or current_odds is None:
        return []

    return [
        "",
        "⚖️ *Comparativo de Odds*",
        f"• Odd justa do modelo: *{fair_odds:.2f}*",
        f"• Odd atual do mercado: *{current_odds:.2f}*",
    ]


def _format_value_bet(analysis: dict) -> list[str]:
    value_bet = _resolve_value_bet(analysis)
    if not value_bet.get("has_value"):
        return []

    details = _resolve_value_bet_details(analysis)
    if not details:
        return []

    market = str(details.get("market") or _resolve_final_pick(analysis)).upper()
    label = details.get("label") or _pick_label(market)
    odds = _safe_float(details.get("odds"))
    fair_odds = _safe_float(details.get("fair_odds"))
    model_prob = _safe_float(details.get("model_prob"))
    implied_prob = _safe_float(details.get("implied_prob"))
    edge = _safe_float(details.get("edge"))

    lines = [
        "",
        "💰 *Value Bet Detectado*",
        f"• Mercado: *{_md(label)}* \\({_md(market)}\\)",
    ]

    if odds is not None:
        lines.append(f"• Odd atual: *{odds:.2f}*")
    if fair_odds is not None:
        lines.append(f"• Odd justa: *{fair_odds:.2f}*")
    if model_prob is not None:
        lines.append(f"• Prob. modelo: *{model_prob:.0%}*")
    if implied_prob is not None:
        lines.append(f"• Prob. implícita: *{implied_prob:.0%}*")
    if edge is not None:
        lines.append(f"• Edge: *{edge:.2%}*")

    return lines


def _format_clv(item: dict) -> list[str]:
    clv = item.get("clv")
    if not clv:
        return []

    open_odds = _safe_float(clv.get("opening_odds"))
    close_odds = _safe_float(clv.get("closing_odds"))
    movement = _safe_float(clv.get("movement"))

    if open_odds is None or close_odds is None:
        return []

    lines = [
        "",
        "📌 *Closing Line Value*",
        f"• Odd no alerta: *{open_odds:.2f}*",
        f"• Odd mais recente: *{close_odds:.2f}*",
    ]

    if movement is not None:
        if movement > 0:
            lines.append(f"• Movimento: *\\+{movement:.2f}*")
        else:
            lines.append(f"• Movimento: *{movement:.2f}*")

    if close_odds < open_odds:
        lines.append("• Leitura: *mercado confirmou o lado do bot*")
    elif close_odds > open_odds:
        lines.append("• Leitura: *mercado andou contra o lado do bot*")
    else:
        lines.append("• Leitura: *linha estável*")

    return lines


def format_prediction_message(payload: dict) -> str:
    fixture = payload["fixture"]
    analysis = payload["analysis"]
    league_name = payload["league"]["display_name"]
    emoji = _league_emoji(league_name)

    local_date, local_time = format_local_datetime(
        fixture["date"],
        fixture["time"],
    )
    local_time = local_time[:5] if local_time else "--:--"

    home_team = fixture["home_team"]
    away_team = fixture["away_team"]

    market_type = _resolve_market_type(analysis)
    final_pick = _resolve_final_pick(analysis)

    lines = [
        "📊 *ANÁLISE PRÉ\\-JOGO*",
        "",
        f"{emoji} *{_md(league_name)}*",
        f"⚽ *{_md(home_team)} x {_md(away_team)}*",
        f"🕒 {_md(local_date)} • {_md(local_time)}",
        "",
    ]

    if analysis.get("home_rank") and analysis.get("away_rank"):
        lines.append(
            f"📍 *Tabela:* #{analysis['home_rank']} vs #{analysis['away_rank']}"
        )
        lines.append("")

    lines.extend(_format_probabilities(analysis))
    lines.extend([
        "",
        f"🎯 *Mercado escolhido:* {_md(_market_type_label(market_type))}",
        f"📌 *Palpite:* {_md(_pick_label(final_pick))} \\({_md(final_pick)}\\)",
        f"🔒 *Confiança:* {_md(_confidence_label(analysis.get('confidence')))}",
        f"🧠 *Modelo:* {_md(str(analysis.get('model_source', 'heuristic')).upper())}",
    ])

    best_probability = _get_best_probability(analysis)
    if best_probability is not None:
        lines.append(f"📈 *Probabilidade da entrada:* {best_probability:.0%}")

    lines.extend(_format_odds(analysis))
    lines.extend(_format_odds_comparison(analysis))
    lines.extend(_format_value_bet(analysis))

    return "\n".join(lines)


def format_best_pick(payload: dict) -> str:
    fixture = payload["fixture"]
    analysis = payload["analysis"]
    league_name = payload["league"]["display_name"]
    emoji = _league_emoji(league_name)

    local_time = _time_only(fixture["date"], fixture["time"])
    home_team = fixture["home_team"]
    away_team = fixture["away_team"]

    market_type = _resolve_market_type(analysis)
    final_pick = _resolve_final_pick(analysis)
    market_odds = _get_pick_market_odds(analysis)
    fair_odds = _get_pick_fair_odds(analysis)
    edge = _get_pick_edge(analysis)

    lines = [
        "🔥 *APOSTA MAIS FORTE DO DIA*",
        "",
        f"{emoji} *{_md(league_name)}*",
        f"⚽ *{_md(home_team)} x {_md(away_team)}*",
        f"🕒 {_md(local_time)}",
        "",
    ]

    lines.extend(_format_probabilities(analysis))
    lines.extend([
        "",
        f"🎯 *Mercado:* {_md(_market_type_label(market_type))}",
        f"📌 *Entrada sugerida:* {_md(_pick_label(final_pick))} \\({_md(final_pick)}\\)",
        f"🔒 *Confiança:* {_md(_confidence_label(analysis.get('confidence')))}",
        f"🧠 *Modelo:* {_md(str(analysis.get('model_source', 'heuristic')).upper())}",
    ])

    best_probability = _get_best_probability(analysis)
    if best_probability is not None:
        lines.append(f"📈 *Probabilidade da entrada:* {best_probability:.0%}")

    if market_odds is not None:
        lines.append(f"📉 *Odd atual:* {market_odds:.2f}")

    if fair_odds is not None:
        lines.append(f"⚖️ *Odd justa:* {fair_odds:.2f}")

    if edge is not None:
        lines.append(f"💰 *Edge:* {edge:.2%}")

    if analysis.get("value_bet", {}).get("has_value"):
        lines.append("✅ *Value bet detectado*")

    return "\n".join(lines)


def format_top_ranking(payloads: list[dict], top_n: int = 5) -> str:
    if not payloads:
        return "📭 *TOP PALPITES DO DIA*\n\nNenhum jogo encontrado\\."

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    top_items = payloads[:top_n]

    lines = ["📊 *TOP PALPITES DO DIA*", ""]

    for idx, payload in enumerate(top_items):
        fixture = payload["fixture"]
        analysis = payload["analysis"]
        league_name = payload["league"]["display_name"]
        emoji = _league_emoji(league_name)
        marker = medals[idx] if idx < len(medals) else f"{idx + 1}\\."
        value_flag = " 💰" if analysis.get("value_bet", {}).get("has_value") else ""

        home_team = fixture["home_team"]
        away_team = fixture["away_team"]

        final_pick = _resolve_final_pick(analysis)
        market_type = _resolve_market_type(analysis)
        market_odds = _get_pick_market_odds(analysis)
        edge = _get_pick_edge(analysis)
        best_probability = _get_best_probability(analysis)

        lines.append(f"{marker} *{_md(home_team)} x {_md(away_team)}*{value_flag}")
        lines.append(
            f"{emoji} {_md(league_name)} • "
            f"{_md(_time_only(fixture['date'], fixture['time']))}"
        )
        lines.append(
            f"Mercado: *{_md(_market_type_label(market_type))}* • "
            f"Palpite: *{_md(_pick_label(final_pick))}* • "
            f"Confiança: *{_md(_confidence_label(analysis.get('confidence')))}*"
        )

        extras = []
        if best_probability is not None:
            extras.append(f"Prob: *{best_probability:.0%}*")
        if market_odds is not None:
            extras.append(f"Odd: *{market_odds:.2f}*")
        if edge is not None:
            extras.append(f"Edge: *{edge:.2%}*")

        if extras:
            lines.append(" • ".join(extras))

        lines.append("")

    return "\n".join(lines).strip()


def group_payloads_by_league(payloads: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for payload in payloads:
        grouped[payload["league"]["display_name"]].append(payload)
    return dict(grouped)


def format_league_summary(league_name: str, payloads: list[dict]) -> str:
    if not payloads:
        return f"🏆 *{_md(league_name.upper())}*\n\nNenhum jogo encontrado\\."

    emoji = _league_emoji(league_name)
    lines = [f"{emoji} *{_md(league_name.upper())}*", ""]

    for payload in payloads:
        fixture = payload["fixture"]
        analysis = payload["analysis"]
        value_flag = " 💰" if analysis.get("value_bet", {}).get("has_value") else ""

        home_team = fixture["home_team"]
        away_team = fixture["away_team"]

        final_pick = _resolve_final_pick(analysis)
        market_type = _resolve_market_type(analysis)
        market_odds = _get_pick_market_odds(analysis)
        edge = _get_pick_edge(analysis)

        lines.append(f"⚽ *{_md(home_team)} x {_md(away_team)}*{value_flag}")
        lines.append(f"🕒 {_md(_time_only(fixture['date'], fixture['time']))}")
        lines.append(
            f"🎯 *{_md(_pick_label(final_pick))}* \\| "
            f"📦 *{_md(_market_type_label(market_type))}* \\| "
            f"🔒 *{_md(_confidence_label(analysis.get('confidence')))}*"
        )
        lines.append(
            f"📈 1X2: {_get_main_probabilities_text(analysis)}"
        )

        if _has_double_chance_probabilities(analysis):
            lines.append(
                f"🧩 DH: {float(analysis.get('prob_1x') or 0):.0%} • "
                f"{float(analysis.get('prob_x2') or 0):.0%} • "
                f"{float(analysis.get('prob_12') or 0):.0%}"
            )

        extras = []
        if market_odds is not None:
            extras.append(f"Odd {market_odds:.2f}")
        if edge is not None:
            extras.append(f"Edge {edge:.2%}")
        if extras:
            lines.append(f"💹 {_md(' | '.join(extras))}")

        if analysis.get("home_rank") and analysis.get("away_rank"):
            lines.append(f"📍 Tabela: #{analysis['home_rank']} vs #{analysis['away_rank']}")

        lines.append("")

    return "\n".join(lines).strip()


def format_result_message(item: dict, ai_summary: str | None = None) -> str:
    status = item.get("status")
    status_emoji = "✅" if status == "hit" else "❌"
    status_label = "ACERTAMOS" if status == "hit" else "ERRAMOS"

    confidence = item.get("confidence", "-")
    league = item.get("league", "Jogo")
    home_team = item.get("home_team", "Casa")
    away_team = item.get("away_team", "Fora")
    pick = str(item.get("pick", "-")).upper()
    real_result = str(item.get("real_result", "-")).upper()
    home_score = item.get("home_score", "-")
    away_score = item.get("away_score", "-")
    market_type = str(item.get("market_type") or "1x2")

    lines = [
        f"{status_emoji} *{status_label}*",
        "",
        f"🏆 *{_md(league)}*",
        f"⚽ *{_md(home_team)} x {_md(away_team)}*",
        f"📊 *Placar final:* {_md(home_score)} x {_md(away_score)}",
        f"🏁 *Resultado:* {_md(_result_label(real_result, home_team, away_team))}",
        "",
        f"📦 *Mercado enviado:* {_md(_market_type_label(market_type))}",
        f"📌 *Palpite enviado:* {_md(_pick_label(pick))} \\({_md(pick)}\\)",
        f"🎯 *Resultado real:* {_md(real_result)}",
        f"🔒 *Confiança do modelo:* {_md(_confidence_label(confidence))}",
    ]

    lines.extend(_format_clv(item))

    if ai_summary:
        lines.extend([
            "",
            "🤖 *Resumo IA*",
            _md(ai_summary.strip()),
        ])

    return "\n".join(lines)


def pick_winner_photo_url(item: dict) -> str | None:
    real_result = item.get("real_result")
    home_badge = item.get("home_badge")
    away_badge = item.get("away_badge")

    if real_result == "1" and home_badge:
        return home_badge

    if real_result == "2" and away_badge:
        return away_badge

    return None