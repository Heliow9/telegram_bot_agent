from collections import defaultdict
from app.services.time_utils import format_local_datetime


LEAGUE_EMOJIS = {
    "Brasileirão Série A": "🇧🇷",
    "Brasileirão Série B": "🇧🇷",
    "Premier League": "🏴",
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


def _escape_markdown(text: str) -> str:
    text = _safe_text(text)

    # seguro tanto para Markdown quanto ajuda bastante no V2
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
        "baixa": "Baixa",
    }
    return mapping.get(str(confidence).lower(), str(confidence))


def _pick_label(pick: str) -> str:
    if pick == "1":
        return "Casa"
    if pick == "2":
        return "Fora"
    if pick == "X":
        return "Empate"
    return str(pick)


def _result_label(real_result: str, home_team: str, away_team: str) -> str:
    if real_result == "1":
        return f"{home_team} venceu"
    if real_result == "2":
        return f"{away_team} venceu"
    if real_result == "X":
        return "Empate"
    return str(real_result)


def _get_pick_market_odds(analysis: dict):
    odds = analysis.get("odds") or {}
    pick = analysis.get("suggested_pick")

    if pick == "1":
        return odds.get("home_odds")
    if pick == "X":
        return odds.get("draw_odds")
    if pick == "2":
        return odds.get("away_odds")
    return None


def _get_pick_fair_odds(analysis: dict):
    fair_odds = analysis.get("fair_odds") or {}
    pick = analysis.get("suggested_pick")
    return fair_odds.get(pick)


def _get_pick_edge(analysis: dict):
    details = (analysis.get("value_bet") or {}).get("details") or {}
    pick = analysis.get("suggested_pick")
    if details.get("market") == pick:
        return details.get("edge")
    return None


def _format_odds(analysis: dict) -> list[str]:
    odds = analysis.get("odds")
    if not odds:
        return []

    lines = [
        "",
        "📉 *Odds 1X2*",
    ]

    if odds.get("home_odds") is not None:
        lines.append(f"• Casa: *{float(odds['home_odds']):.2f}*")
    if odds.get("draw_odds") is not None:
        lines.append(f"• Empate: *{float(odds['draw_odds']):.2f}*")
    if odds.get("away_odds") is not None:
        lines.append(f"• Fora: *{float(odds['away_odds']):.2f}*")

    if odds.get("bookmaker"):
        lines.append(f"• Bookmaker: *{_md(odds['bookmaker'])}*")

    return lines


def _format_odds_comparison(analysis: dict) -> list[str]:
    comparison = analysis.get("odds_comparison")
    if not comparison:
        return []

    fair_odds = comparison.get("fair_odds")
    current_odds = comparison.get("current_odds")

    if fair_odds is None or current_odds is None:
        return []

    return [
        "",
        "⚖️ *Comparativo de Odds*",
        f"• Odd justa do modelo: *{float(fair_odds):.2f}*",
        f"• Odd atual do mercado: *{float(current_odds):.2f}*",
    ]


def _format_value_bet(analysis: dict) -> list[str]:
    value_bet = analysis.get("value_bet") or {}
    if not value_bet.get("has_value"):
        return []

    details = value_bet.get("details") or {}
    if not details:
        return []

    return [
        "",
        "💰 *Value Bet Detectado*",
        f"• Mercado: *{_md(details.get('label'))}* \\({_md(details.get('market'))}\\)",
        f"• Odd atual: *{details.get('odds')}*",
        f"• Odd justa: *{details.get('fair_odds')}*",
        f"• Prob. modelo: *{details.get('model_prob', 0):.0%}*",
        f"• Prob. implícita: *{details.get('implied_prob', 0):.0%}*",
        f"• Edge: *{details.get('edge', 0):.2%}*",
    ]


def _format_clv(item: dict) -> list[str]:
    clv = item.get("clv")
    if not clv:
        return []

    open_odds = clv.get("opening_odds")
    close_odds = clv.get("closing_odds")
    movement = clv.get("movement")

    if open_odds is None or close_odds is None:
        return []

    lines = [
        "",
        "📌 *Closing Line Value*",
        f"• Odd no alerta: *{float(open_odds):.2f}*",
        f"• Odd mais recente: *{float(close_odds):.2f}*",
    ]

    if movement is not None:
        if movement > 0:
            lines.append(f"• Movimento: *\\+{float(movement):.2f}*")
        else:
            lines.append(f"• Movimento: *{float(movement):.2f}*")

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

    lines.extend([
        "*Probabilidades 1X2*",
        f"• Casa: *{analysis['prob_home']:.0%}*",
        f"• Empate: *{analysis['prob_draw']:.0%}*",
        f"• Fora: *{analysis['prob_away']:.0%}*",
        "",
        f"🎯 *Palpite:* {_md(_pick_label(analysis['suggested_pick']))} \\({_md(analysis['suggested_pick'])}\\)",
        f"🔒 *Confiança:* {_md(_confidence_label(analysis['confidence']))}",
        f"🧠 *Modelo:* {_md(analysis.get('model_source', 'heuristic').upper())}",
    ])

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
        "*Probabilidades 1X2*",
        f"• Casa: *{analysis['prob_home']:.0%}*",
        f"• Empate: *{analysis['prob_draw']:.0%}*",
        f"• Fora: *{analysis['prob_away']:.0%}*",
        "",
        f"🎯 *Entrada sugerida:* {_md(_pick_label(analysis['suggested_pick']))} \\({_md(analysis['suggested_pick'])}\\)",
        f"🔒 *Confiança:* {_md(_confidence_label(analysis['confidence']))}",
        f"🧠 *Modelo:* {_md(analysis.get('model_source', 'heuristic').upper())}",
    ]

    if market_odds is not None:
        lines.append(f"📉 *Odd atual:* {float(market_odds):.2f}")

    if fair_odds is not None:
        lines.append(f"⚖️ *Odd justa:* {float(fair_odds):.2f}")

    if edge is not None:
        lines.append(f"💰 *Edge:* {float(edge):.2%}")

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

        market_odds = _get_pick_market_odds(analysis)
        edge = _get_pick_edge(analysis)

        lines.append(f"{marker} *{_md(home_team)} x {_md(away_team)}*{value_flag}")
        lines.append(f"{emoji} {_md(league_name)} • {_md(_time_only(fixture['date'], fixture['time']))}")
        lines.append(
            f"Palpite: *{_md(_pick_label(analysis['suggested_pick']))}* • "
            f"Confiança: *{_md(_confidence_label(analysis['confidence']))}*"
        )

        extras = []
        if market_odds is not None:
            extras.append(f"Odd: *{float(market_odds):.2f}*")
        if edge is not None:
            extras.append(f"Edge: *{float(edge):.2%}*")

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

        market_odds = _get_pick_market_odds(analysis)
        edge = _get_pick_edge(analysis)

        lines.append(f"⚽ *{_md(home_team)} x {_md(away_team)}*{value_flag}")
        lines.append(f"🕒 {_md(_time_only(fixture['date'], fixture['time']))}")
        lines.append(
            f"🎯 *{_md(_pick_label(analysis['suggested_pick']))}* | "
            f"🔒 *{_md(_confidence_label(analysis['confidence']))}*"
        )
        lines.append(
            f"📈 {analysis['prob_home']:.0%} • {analysis['prob_draw']:.0%} • {analysis['prob_away']:.0%}"
        )

        extras = []
        if market_odds is not None:
            extras.append(f"Odd {float(market_odds):.2f}")
        if edge is not None:
            extras.append(f"Edge {float(edge):.2%}")
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
    pick = item.get("pick", "-")
    real_result = item.get("real_result", "-")
    home_score = item.get("home_score", "-")
    away_score = item.get("away_score", "-")

    lines = [
        f"{status_emoji} *{status_label}*",
        "",
        f"🏆 *{_md(league)}*",
        f"⚽ *{_md(home_team)} x {_md(away_team)}*",
        f"📊 *Placar final:* {_md(home_score)} x {_md(away_score)}",
        f"🏁 *Resultado:* {_md(_result_label(real_result, home_team, away_team))}",
        "",
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