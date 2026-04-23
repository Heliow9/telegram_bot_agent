from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.daily_leagues_service import DailyLeaguesService
from app.services.prediction_store import (
    get_prediction_by_fixture_id,
    save_prediction,
)


def run():
    tz = ZoneInfo("America/Recife")
    now_local = datetime.now(tz)

    today = now_local.strftime("%Y-%m-%d")
    yesterday = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

    daily_service = DailyLeaguesService()

    print(f"[SYNC RECENT] Agora: {now_local.isoformat()}")
    print(f"[SYNC RECENT] Buscando dia atual: {today}")
    print(f"[SYNC RECENT] Buscando dia anterior: {yesterday}")

    payloads_today = daily_service.get_all_day_payloads(today)
    payloads_yesterday = daily_service.get_all_day_payloads(yesterday)

    merged = []
    seen = set()

    for payload in payloads_yesterday + payloads_today:
        fixture = payload.get("fixture") or {}
        fixture_id = str(fixture.get("id") or "").strip()

        if not fixture_id:
            continue

        if fixture_id in seen:
            continue

        seen.add(fixture_id)
        merged.append(payload)

    print(f"[SYNC RECENT] Payloads únicos encontrados: {len(merged)}")

    inserted = 0
    skipped_existing = 0
    errors = 0

    for payload in merged:
        fixture = payload.get("fixture") or {}
        fixture_id = str(fixture.get("id") or "").strip()
        home_team = fixture.get("home_team", "Casa")
        away_team = fixture.get("away_team", "Fora")
        match_date = fixture.get("date")

        try:
            existing = get_prediction_by_fixture_id(fixture_id)

            if existing:
                skipped_existing += 1
                print(
                    f"[SYNC RECENT] Já existe | "
                    f"fixture_id={fixture_id} | jogo={home_team} x {away_team} | data={match_date}"
                )
                continue

            save_prediction(payload)
            inserted += 1

            print(
                f"[SYNC RECENT] Inserido | "
                f"fixture_id={fixture_id} | jogo={home_team} x {away_team} | data={match_date}"
            )

        except Exception as e:
            errors += 1
            print(
                f"[SYNC RECENT] Erro | fixture_id={fixture_id} | "
                f"jogo={home_team} x {away_team} | erro={e}"
            )

    result = {
        "today": today,
        "yesterday": yesterday,
        "found_unique": len(merged),
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }

    print(f"[SYNC RECENT] Finalizado: {result}")
    return result


if __name__ == "__main__":
    print(run())