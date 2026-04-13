from collections import defaultdict
from app.services.time_utils import format_local_datetime


LEAGUE_EMOJIS = {
    "Brasileirão Série A": "🇧🇷",
    "Brasileirão Série B": "🇧🇷",
    "Premier League": "🏴",
    "Argentina Liga Profesional": "🇦🇷",
    "Itália Série A": "🇮🇹",
    "Turquia Super Lig": "🇹🇷",
}


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
        "📊 *ANÁLISE PRÉ-JOGO*",
        "",
        f"{emoji} *{league_name}*",
        f"⚽ *{home_team} x {away_team}*",
        f"🕒 {local_date} • {local_time}",
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
        f"🎯 *Palpite:* {_pick_label(analysis['suggested_pick'])} ({analysis['suggested_pick']})",
        f"🔒 *Confiança:* {_confidence_label(analysis['confidence'])}",
    ])

    return "\n".join(lines)


def format_best_pick(payload: dict) -> str:
    fixture = payload["fixture"]
    analysis = payload["analysis"]
    league_name = payload["league"]["display_name"]
    emoji = _league_emoji(league_name)

    local_time = _time_only(fixture["date"], fixture["time"])
    home_team = fixture["home_team"]
    away_team = fixture["away_team"]

    return "\n".join([
        "🔥 *APOSTA MAIS FORTE DO DIA*",
        "",
        f"{emoji} *{league_name}*",
        f"⚽ *{home_team} x {away_team}*",
        f"🕒 {local_time}",
        "",
        "*Probabilidades 1X2*",
        f"• Casa: *{analysis['prob_home']:.0%}*",
        f"• Empate: *{analysis['prob_draw']:.0%}*",
        f"• Fora: *{analysis['prob_away']:.0%}*",
        "",
        f"🎯 *Entrada sugerida:* {_pick_label(analysis['suggested_pick'])} ({analysis['suggested_pick']})",
        f"🔒 *Confiança:* {_confidence_label(analysis['confidence'])}",
    ])


def format_top_ranking(payloads: list[dict], top_n: int = 5) -> str:
    if not payloads:
        return "📭 *TOP PALPITES DO DIA*\n\nNenhum jogo encontrado."

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    top_items = payloads[:top_n]

    lines = ["📊 *TOP PALPITES DO DIA*", ""]

    for idx, payload in enumerate(top_items):
        fixture = payload["fixture"]
        analysis = payload["analysis"]
        league_name = payload["league"]["display_name"]
        emoji = _league_emoji(league_name)
        marker = medals[idx] if idx < len(medals) else f"{idx + 1}."

        home_team = fixture["home_team"]
        away_team = fixture["away_team"]

        lines.append(f"{marker} *{home_team} x {away_team}*")
        lines.append(f"{emoji} {league_name} • {_time_only(fixture['date'], fixture['time'])}")
        lines.append(
            f"Palpite: *{_pick_label(analysis['suggested_pick'])}* • "
            f"Confiança: *{_confidence_label(analysis['confidence'])}*"
        )
        lines.append("")

    return "\n".join(lines).strip()


def group_payloads_by_league(payloads: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for payload in payloads:
        grouped[payload["league"]["display_name"]].append(payload)
    return dict(grouped)


def format_league_summary(league_name: str, payloads: list[dict]) -> str:
    if not payloads:
        return f"🏆 *{league_name.upper()}*\n\nNenhum jogo encontrado."

    emoji = _league_emoji(league_name)
    lines = [f"{emoji} *{league_name.upper()}*", ""]

    for payload in payloads:
        fixture = payload["fixture"]
        analysis = payload["analysis"]

        home_team = fixture["home_team"]
        away_team = fixture["away_team"]

        lines.append(f"⚽ *{home_team} x {away_team}*")
        lines.append(f"🕒 {_time_only(fixture['date'], fixture['time'])}")
        lines.append(
            f"🎯 *{_pick_label(analysis['suggested_pick'])}* | "
            f"🔒 *{_confidence_label(analysis['confidence'])}*"
        )
        lines.append(
            f"📈 {analysis['prob_home']:.0%} • {analysis['prob_draw']:.0%} • {analysis['prob_away']:.0%}"
        )

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
        f"🏆 *{league}*",
        f"⚽ *{home_team} x {away_team}*",
        f"📊 *Placar final:* {home_score} x {away_score}",
        f"🏁 *Resultado:* {_result_label(real_result, home_team, away_team)}",
        "",
        f"📌 *Palpite enviado:* {_pick_label(pick)} ({pick})",
        f"🎯 *Resultado real:* {real_result}",
        f"🔒 *Confiança do modelo:* {_confidence_label(confidence)}",
    ]

    if ai_summary:
        lines.extend([
            "",
            "🤖 *Resumo IA*",
            ai_summary.strip(),
        ])

    return "\n".join(lines)


def pick_winner_photo_url(item: dict) -> str | None:
    """
    Escolhe a imagem do vencedor.
    Espera que o item possa ter:
    - home_badge
    - away_badge
    """
    real_result = item.get("real_result")
    home_badge = item.get("home_badge")
    away_badge = item.get("away_badge")

    if real_result == "1" and home_badge:
        return home_badge

    if real_result == "2" and away_badge:
        return away_badge

    # empate: sem vencedor claro
    return None