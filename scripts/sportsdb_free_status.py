from __future__ import annotations

import argparse
import json
from datetime import datetime

from app.services.sportsdb_api import SportsDBAPI


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico do gateway local TheSportsDB")
    parser.add_argument("--probe", action="store_true", help="faz uma única consulta Basketball para a data")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    api = SportsDBAPI()
    print(json.dumps({"status": api.status()}, ensure_ascii=False, indent=2))

    if args.probe:
        data = api.events_by_day_sport(args.date, "Basketball")
        events = api.get_events_list(data)
        print(json.dumps({
            "probe_date": args.date,
            "events": len(events),
            "error": data.get("error") if isinstance(data, dict) else None,
            "rate_limited": data.get("rate_limited") if isinstance(data, dict) else None,
            "details": data.get("details") if isinstance(data, dict) else None,
            "status_after": api.status(),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
