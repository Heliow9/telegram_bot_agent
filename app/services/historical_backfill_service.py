from datetime import timedelta
from typing import List, Dict
from app.constants import LEAGUES
from app.services.time_utils import now_local, event_to_local_datetime
from app.services.sportsdb_api import SportsDBAPI


class HistoricalBackfillService:
    def __init__(self):
        self.api = SportsDBAPI()

    def _cutoff_date(self):
        return now_local() - timedelta(days=365)

    def _is_recent_enough(self, event: Dict) -> bool:
        dt_local = event_to_local_datetime(
            event.get("dateEvent", ""),
            event.get("strTime", ""),
        )

        if dt_local is None:
            print(
                f"[BACKFILL][SKIP_DATE_PARSE] "
                f"id={event.get('idEvent')} "
                f"date={event.get('dateEvent')} "
                f"time={event.get('strTime')}"
            )
            return False

        cutoff = self._cutoff_date()
        is_recent = dt_local >= cutoff

        if not is_recent:
            print(
                f"[BACKFILL][SKIP_OLD] "
                f"id={event.get('idEvent')} "
                f"dt_local={dt_local} "
                f"cutoff={cutoff}"
            )

        return is_recent

    def _is_finished_event(self, event: Dict) -> bool:
        status = (event.get("strStatus") or "").strip().upper()

        if status in {
            "FT",
            "AET",
            "PEN",
            "FULL TIME",
            "MATCH FINISHED",
            "AFTER EXTRA TIME",
            "AFTER PENALTIES",
            "FINISHED",
        }:
            return True

        home_score = event.get("intHomeScore")
        away_score = event.get("intAwayScore")

        # fallback: se já tem placar numérico, considera finalizado
        try:
            if home_score is not None and away_score is not None:
                int(home_score)
                int(away_score)
                return True
        except (TypeError, ValueError):
            pass

        print(
            f"[BACKFILL][SKIP_NOT_FINISHED] "
            f"id={event.get('idEvent')} "
            f"status={event.get('strStatus')} "
            f"score={home_score}-{away_score}"
        )
        return False

    def get_recent_finished_events_for_league(self, league_meta: Dict) -> List[Dict]:
        season = league_meta["season"]
        league_id = league_meta["id"]

        events = self.api.get_events_by_season_list(
            league_id=str(league_id),
            season=str(season),
        )

        print(
            f"[BACKFILL][DEBUG] {league_meta['display_name']} "
            f"league_id={league_id} season={season} total_api={len(events)}"
        )

        if events:
            sample = events[0]
            print(
                f"[BACKFILL][SAMPLE] "
                f"id={sample.get('idEvent')} "
                f"date={sample.get('dateEvent')} "
                f"time={sample.get('strTime')} "
                f"status={sample.get('strStatus')} "
                f"score={sample.get('intHomeScore')}-{sample.get('intAwayScore')}"
            )

        filtered = []
        for event in events:
            if not self._is_recent_enough(event):
                continue
            if not self._is_finished_event(event):
                continue
            filtered.append(event)

        print(
            f"[BACKFILL][FILTERED] {league_meta['display_name']} "
            f"aprovados={len(filtered)} de total_api={len(events)}"
        )

        return filtered

    def get_all_recent_finished_events(self) -> List[Dict]:
        all_events = []

        for league_meta in LEAGUES:
            try:
                events = self.get_recent_finished_events_for_league(league_meta)
                for event in events:
                    event["_league_meta"] = league_meta
                all_events.extend(events)
                print(f"[BACKFILL] {league_meta['display_name']}: {len(events)} jogos")
            except Exception as e:
                print(f"[BACKFILL] Erro na liga {league_meta['display_name']}: {e}")

        return all_events