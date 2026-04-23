from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple

from app.constants import LEAGUES
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.event_selector import (
    filter_morning_events,
    filter_afternoon_events,
    filter_night_events,
    filter_events_starting_in_30_minutes,
)


class DailyLeaguesService:
    def __init__(self):
        self.api = SportsDBAPI()
        self.analysis_service = AnalysisService()
        self.tz = ZoneInfo("America/Recife")

    def _now_local(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> str:
        return self._now_local().strftime("%Y-%m-%d")

    def _normalize_time(self, raw_time: str) -> str:
        normalized_time = str(raw_time or "").strip()

        if not normalized_time:
            return "00:00:00"

        normalized_time = normalized_time.replace("Z", "")

        if "+" in normalized_time:
            normalized_time = normalized_time.split("+", 1)[0]

        if normalized_time.count(":") == 1:
            normalized_time = f"{normalized_time}:00"

        return normalized_time

    def _parse_datetime_with_tz(
        self,
        date_str: str,
        time_str: str,
        tz: ZoneInfo,
    ) -> Optional[datetime]:
        if not date_str:
            return None

        normalized_time = self._normalize_time(time_str)
        raw_value = f"{date_str} {normalized_time}"

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(raw_value, fmt).replace(tzinfo=tz)
            except ValueError:
                continue

        return None

    def _parse_local_datetime_from_event(self, event: Dict) -> Optional[datetime]:
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        time_event_local = str(event.get("strTimeLocal") or "").strip()

        if date_event_local:
            return self._parse_datetime_with_tz(
                date_event_local,
                time_event_local,
                self.tz,
            )

        return None

    def _parse_utc_event_as_local(self, event: Dict) -> Optional[datetime]:
        date_event = str(event.get("dateEvent") or "").strip()
        time_event = str(event.get("strTime") or "").strip()

        dt_utc = self._parse_datetime_with_tz(
            date_event,
            time_event,
            ZoneInfo("UTC"),
        )

        if dt_utc is None:
            return None

        return dt_utc.astimezone(self.tz)

    def _is_event_for_target_local_date(self, event: Dict, target_date: str) -> bool:
        # 1) Prioridade para a data local já fornecida pela API
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        if date_event_local:
            return date_event_local == target_date

        # 2) Se tiver datetime local montável, usa isso
        local_dt = self._parse_local_datetime_from_event(event)
        if local_dt is not None:
            return local_dt.strftime("%Y-%m-%d") == target_date

        # 3) Fallback seguro: converte dateEvent + strTime (UTC) para local
        utc_as_local = self._parse_utc_event_as_local(event)
        if utc_as_local is not None:
            return utc_as_local.strftime("%Y-%m-%d") == target_date

        # 4) Último fallback bruto
        date_event = str(event.get("dateEvent") or "").strip()
        return date_event == target_date

    def _dedupe_events(self, events: List[Dict]) -> List[Dict]:
        deduped = []
        seen = set()

        for event in events or []:
            event_id = str(event.get("idEvent") or "").strip()
            compound = (
                event_id,
                str(event.get("strHomeTeam") or "").strip().lower(),
                str(event.get("strAwayTeam") or "").strip().lower(),
                str(event.get("dateEvent") or event.get("dateEventLocal") or "").strip(),
                str(event.get("strTime") or event.get("strTimeLocal") or "").strip(),
            )
            if compound in seen:
                continue
            seen.add(compound)
            deduped.append(event)

        return deduped

    def _events_for_league_on_date(self, league_meta: Dict, date_str: str) -> List[Dict]:
        raw_events: List[Dict] = []

        # 1) Busca principal por nome da liga
        try:
            by_name = self.api.get_events_by_day_list(date_str, league_meta["name"])
            if by_name:
                raw_events.extend(by_name)
        except Exception as e:
            print(f"[DAILY] Falha eventsday por nome em {league_meta['display_name']}: {e}")

        # 2) Fallback por próximos jogos da liga (ajuda ligas como Copa do Brasil)
        try:
            by_next = self.api.get_next_events_by_league_list(str(league_meta["id"]))
            if by_next:
                raw_events.extend(by_next)
        except Exception as e:
            print(f"[DAILY] Falha eventsnextleague em {league_meta['display_name']}: {e}")

        # 3) Fallback por temporada inteira
        try:
            by_season = self.api.get_events_by_season_list(
                str(league_meta["id"]),
                str(league_meta["season"]),
            )
            if by_season:
                raw_events.extend(by_season)
        except Exception as e:
            print(f"[DAILY] Falha eventsseason em {league_meta['display_name']}: {e}")

        raw_events = self._dedupe_events(raw_events)
        filtered_events = []

        for event in raw_events:
            if self._is_event_for_target_local_date(event, date_str):
                filtered_events.append(event)
            else:
                parsed_local = self._parse_local_datetime_from_event(event)
                parsed_utc_as_local = self._parse_utc_event_as_local(event)

                print(
                    f"[DAILY][DROP] {league_meta['display_name']} | "
                    f"evento={event.get('strEvent')} | "
                    f"dateEvent={event.get('dateEvent')} {event.get('strTime')} | "
                    f"dateEventLocal={event.get('dateEventLocal')} {event.get('strTimeLocal')} | "
                    f"parsedLocal={parsed_local.isoformat() if parsed_local else None} | "
                    f"utcAsLocal={parsed_utc_as_local.isoformat() if parsed_utc_as_local else None}"
                )

        print(
            f"[DAILY] {league_meta['display_name']} | "
            f"data={date_str} | retornados={len(raw_events)} | "
            f"filtrados_dia_local={len(filtered_events)}"
        )

        return self._dedupe_events(filtered_events)

    def _select_events(self, events: List[Dict], selector_name: str) -> Tuple[List[Dict], str]:
        if selector_name == "morning":
            return filter_morning_events(events), "Manhã"

        if selector_name == "afternoon":
            return filter_afternoon_events(events), "Tarde"

        if selector_name == "night":
            return filter_night_events(events), "Noite"

        if selector_name == "30min":
            return (
                filter_events_starting_in_30_minutes(
                    events,
                    min_minutes=28,
                    max_minutes=31,
                ),
                "Janela 30min",
            )

        if selector_name in ("all_day", "full_day", "day_full"):
            return events, "Dia inteiro"

        return [], selector_name

    def _build_payloads_for_date(
        self,
        date_str: str,
        selector_name: str,
    ) -> List[Dict]:
        payloads = []

        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_on_date(league_meta, date_str)
                selected, label = self._select_events(events, selector_name)

                if selected:
                    print(
                        f"[DAILY] {label} | {league_meta['display_name']} | "
                        f"data={date_str} | eventos encontrados: {len(selected)}"
                    )

                built_payloads = self.analysis_service.build_many_analyses(
                    selected,
                    league_meta,
                )

                if built_payloads:
                    print(
                        f"[DAILY] {label} | {league_meta['display_name']} | "
                        f"payloads gerados: {len(built_payloads)}"
                    )

                payloads.extend(built_payloads)

            except Exception as e:
                print(
                    f"[DAILY] Erro {selector_name} em "
                    f"{league_meta['display_name']} | data={date_str}: {e}"
                )
                continue

        return self.analysis_service.sort_by_best_picks(payloads)

    def get_all_day_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "all_day")

    def get_full_day_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "all_day")

    def get_morning_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "morning")

    def get_afternoon_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "afternoon")

    def get_30min_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "30min")

    def get_night_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "night")
