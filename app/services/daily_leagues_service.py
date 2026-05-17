from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple
import unicodedata

from app.constants import LEAGUES
from app.services.sportsdb_api import SportsDBAPI
from app.services.analysis_service import AnalysisService
from app.services.time_utils import event_payload_to_local_datetime
from app.services.event_selector import (
    filter_morning_events,
    filter_afternoon_events,
    filter_night_events,
    filter_events_starting_in_30_minutes,
)


class DailyLeaguesService:
    """Coleta e filtra jogos elegíveis para grades, pré-live e radar.

    Melhorias importantes:
    - usa eventsday por liga e também fallback por esporte/data;
    - filtra localmente por liga, data e janela futura;
    - descarta eventos sem kickoff confiável, passados ou finalizados;
    - usa janela móvel para preload/radar quando a data exata vem vazia;
    - reduz ruído de temporada inteira trazendo jogos antigos.
    """

    FINISHED_STATUSES = {
        "ft", "aet", "pen", "finished", "match finished", "full time",
        "after extra time", "after penalties", "cancelled", "canceled", "postponed",
        "abandoned", "walkover", "award",
    }

    def __init__(self):
        self.api = SportsDBAPI()
        self.analysis_service = AnalysisService()
        self.tz = ZoneInfo("America/Recife")

    def _now_local(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> str:
        return self._now_local().strftime("%Y-%m-%d")

    def _normalize_text(self, value: str) -> str:
        value = str(value or "").strip()
        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = value.lower()
        value = value.replace("-", " ")
        value = value.replace("_", " ")
        value = " ".join(value.split())
        return value

    def _normalize_time(self, raw_time: str) -> str:
        normalized_time = str(raw_time or "").strip()
        if not normalized_time:
            return "00:00:00"
        normalized_time = normalized_time.replace("Z", "")
        if "+" in normalized_time:
            normalized_time = normalized_time.split("+", 1)[0]
        if "T" in normalized_time:
            normalized_time = normalized_time.split("T", 1)[-1]
        if normalized_time.count(":") == 1:
            normalized_time = f"{normalized_time}:00"
        return normalized_time

    def _parse_datetime_with_tz(self, date_str: str, time_str: str, tz: ZoneInfo) -> Optional[datetime]:
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
            return self._parse_datetime_with_tz(date_event_local, time_event_local, self.tz)
        return None

    def _parse_utc_event_as_local(self, event: Dict) -> Optional[datetime]:
        date_event = str(event.get("dateEvent") or "").strip()
        time_event = str(event.get("strTime") or "").strip()
        dt_utc = self._parse_datetime_with_tz(date_event, time_event, ZoneInfo("UTC"))
        if dt_utc is None:
            return None
        return dt_utc.astimezone(self.tz)

    def _event_local_dt(self, event: Dict) -> Optional[datetime]:
        return event_payload_to_local_datetime(event)

    def _is_finished_event(self, event: Dict) -> bool:
        status = self._normalize_text(event.get("strStatus") or event.get("strProgress") or "")
        if not status:
            return False
        if status in self.FINISHED_STATUSES:
            return True
        return any(word in status for word in ("finished", "final", "cancel", "postpon", "abandon"))

    def _event_matches_league(self, event: Dict, league_meta: Dict) -> bool:
        event_league_id = str(event.get("idLeague") or "").strip()
        if event_league_id and event_league_id == str(league_meta.get("id") or "").strip():
            return True

        event_league = self._normalize_text(event.get("strLeague") or "")
        wanted_names = {
            self._normalize_text(league_meta.get("name")),
            self._normalize_text(league_meta.get("display_name")),
            self._normalize_text(league_meta.get("key")),
        }
        wanted_names = {x for x in wanted_names if x}

        if not event_league:
            return False

        if event_league in wanted_names:
            return True

        # Match tolerante para diferenças pequenas de nomenclatura.
        for wanted in wanted_names:
            if wanted and (wanted in event_league or event_league in wanted):
                return True

        return False

    def _is_event_for_target_local_date(self, event: Dict, target_date: str) -> bool:
        local_dt = self._event_local_dt(event)
        if local_dt is not None:
            return local_dt.strftime("%Y-%m-%d") == target_date
        date_event = str(event.get("dateEvent") or "").strip()
        date_event_local = str(event.get("dateEventLocal") or "").strip()
        return target_date in {date_event, date_event_local}

    def _is_future_window(self, event: Dict, start_dt: datetime, end_dt: datetime) -> bool:
        if self._is_finished_event(event):
            return False
        local_dt = self._event_local_dt(event)
        if local_dt is None:
            return False
        return start_dt <= local_dt <= end_dt

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

    def _date_range(self, start_date: str, days: int) -> List[str]:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

    def _collect_raw_events_for_dates(self, league_meta: Dict, dates: List[str]) -> List[Dict]:
        raw_events: List[Dict] = []
        for date_str in dates:
            try:
                by_name = self.api.get_events_by_day_list(date_str, league_meta["name"])
                if by_name:
                    raw_events.extend(by_name)
                    print(f"[DAILY][SOURCE] {league_meta['display_name']} | eventsday:l | data={date_str} | qtd={len(by_name)}")
            except Exception as e:
                print(f"[DAILY] Falha eventsday por nome em {league_meta['display_name']} data={date_str}: {e}")

            try:
                by_sport = self.api.get_events_by_day_sport_list(date_str, sport="Soccer")
                if by_sport:
                    league_filtered = [ev for ev in by_sport if self._event_matches_league(ev, league_meta)]
                    raw_events.extend(league_filtered)
                    print(
                        f"[DAILY][SOURCE] {league_meta['display_name']} | eventsday:soccer | "
                        f"data={date_str} | retornados={len(by_sport)} | liga={len(league_filtered)}"
                    )
            except Exception as e:
                print(f"[DAILY] Falha eventsday por esporte em {league_meta['display_name']} data={date_str}: {e}")

        return self._dedupe_events(raw_events)

    def _collect_next_events(self, league_meta: Dict) -> List[Dict]:
        raw_events: List[Dict] = []
        try:
            by_next = self.api.get_next_events_by_league_list(str(league_meta["id"]))
            if by_next:
                raw_events.extend(by_next)
                print(f"[DAILY][SOURCE] {league_meta['display_name']} | eventsnextleague | qtd={len(by_next)}")
        except Exception as e:
            print(f"[DAILY] Falha eventsnextleague em {league_meta['display_name']}: {e}")
        return self._dedupe_events(raw_events)

    def _events_for_league_on_date(self, league_meta: Dict, date_str: str) -> List[Dict]:
        raw_events = self._collect_raw_events_for_dates(league_meta, [date_str])

        # Fallback controlado: só usa próximos jogos da liga, nunca temporada inteira,
        # e ainda assim filtra pela data local alvo. Isso evita trazer partidas antigas.
        if not raw_events:
            raw_events.extend(self._collect_next_events(league_meta))
            raw_events = self._dedupe_events(raw_events)

        filtered_events = []
        now = self._now_local()

        for event in raw_events:
            local_dt = self._event_local_dt(event)
            keep = (
                self._event_matches_league(event, league_meta)
                and self._is_event_for_target_local_date(event, date_str)
                and not self._is_finished_event(event)
                and (local_dt is None or local_dt >= now - timedelta(minutes=5))
            )

            if keep:
                filtered_events.append(event)
            else:
                parsed_local = self._parse_local_datetime_from_event(event)
                parsed_utc_as_local = self._parse_utc_event_as_local(event)
                reason = []
                if not self._event_matches_league(event, league_meta):
                    reason.append("league_mismatch")
                if not self._is_event_for_target_local_date(event, date_str):
                    reason.append("date_mismatch")
                if self._is_finished_event(event):
                    reason.append("finished")
                if local_dt is not None and local_dt < now - timedelta(minutes=5):
                    reason.append("past")
                print(
                    f"[DAILY][DROP] {league_meta['display_name']} | motivo={','.join(reason) or 'unknown'} | "
                    f"evento={event.get('strEvent')} | league={event.get('strLeague')} | "
                    f"dateEvent={event.get('dateEvent')} {event.get('strTime')} | "
                    f"dateEventLocal={event.get('dateEventLocal')} {event.get('strTimeLocal')} | "
                    f"parsedLocal={parsed_local.isoformat() if parsed_local else None} | "
                    f"utcAsLocal={parsed_utc_as_local.isoformat() if parsed_utc_as_local else None}"
                )

        print(
            f"[DAILY] {league_meta['display_name']} | data={date_str} | retornados={len(raw_events)} | "
            f"filtrados_dia_local={len(filtered_events)}"
        )
        return self._dedupe_events(filtered_events)

    def _events_for_league_in_window(self, league_meta: Dict, hours: int = 48) -> List[Dict]:
        now = self._now_local()
        end = now + timedelta(hours=hours)
        days = max(1, (end.date() - now.date()).days + 1)
        dates = self._date_range(now.strftime("%Y-%m-%d"), days)

        raw_events = self._collect_raw_events_for_dates(league_meta, dates)
        raw_events.extend(self._collect_next_events(league_meta))
        raw_events = self._dedupe_events(raw_events)

        filtered = []
        drops = 0
        for event in raw_events:
            if not self._event_matches_league(event, league_meta):
                drops += 1
                continue
            if self._is_future_window(event, now, end):
                filtered.append(event)
            else:
                drops += 1

        print(
            f"[UPCOMING] {league_meta['display_name']} | janela={hours}h | "
            f"retornados={len(raw_events)} | futuros_validos={len(filtered)} | drops={drops}"
        )
        return self._dedupe_events(filtered)

    def _select_events(self, events: List[Dict], selector_name: str) -> Tuple[List[Dict], str]:
        if selector_name == "morning":
            return filter_morning_events(events), "Manhã"
        if selector_name == "afternoon":
            return filter_afternoon_events(events), "Tarde"
        if selector_name == "night":
            return filter_night_events(events), "Noite"
        if selector_name == "30min":
            return filter_events_starting_in_30_minutes(events, min_minutes=0, max_minutes=30), "Janela 30min"
        if selector_name in ("all_day", "full_day", "day_full"):
            return events, "Dia inteiro"
        if selector_name == "upcoming":
            return events, "Próximas horas"
        return [], selector_name

    def _build_payloads_for_date(self, date_str: str, selector_name: str) -> List[Dict]:
        payloads = []
        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_on_date(league_meta, date_str)
                selected, label = self._select_events(events, selector_name)
                if selected:
                    print(f"[DAILY] {label} | {league_meta['display_name']} | data={date_str} | eventos encontrados: {len(selected)}")
                built_payloads = self.analysis_service.build_many_analyses(selected, league_meta)
                if built_payloads:
                    print(f"[DAILY] {label} | {league_meta['display_name']} | payloads gerados: {len(built_payloads)}")
                payloads.extend(built_payloads)
            except Exception as e:
                print(f"[DAILY] Erro {selector_name} em {league_meta['display_name']} | data={date_str}: {e}")
                continue
        return self.analysis_service.sort_by_best_picks(payloads)

    def get_upcoming_payloads(self, hours: int = 48) -> List[Dict]:
        payloads = []
        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_in_window(league_meta, hours=hours)
                if events:
                    print(f"[UPCOMING] {league_meta['display_name']} | eventos encontrados: {len(events)}")
                built_payloads = self.analysis_service.build_many_analyses(events, league_meta)
                if built_payloads:
                    print(f"[UPCOMING] {league_meta['display_name']} | payloads gerados: {len(built_payloads)}")
                payloads.extend(built_payloads)
            except Exception as e:
                print(f"[UPCOMING] Erro em {league_meta['display_name']} | janela={hours}h: {e}")
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
        # Pré-live deve ser janela móvel, não apenas data exata, para não perder jogos
        # perto da meia-noite ou quando a API usa data UTC/local diferente.
        events_by_league = []
        now = self._now_local()
        end = now + timedelta(minutes=30)
        for league_meta in sorted(LEAGUES, key=lambda x: x["priority"]):
            try:
                events = self._events_for_league_in_window(league_meta, hours=2)
                selected = [ev for ev in events if self._is_future_window(ev, now, end)]
                built_payloads = self.analysis_service.build_many_analyses(selected, league_meta)
                events_by_league.extend(built_payloads)
            except Exception as e:
                print(f"[DAILY] Erro 30min móvel em {league_meta['display_name']}: {e}")
        return self.analysis_service.sort_by_best_picks(events_by_league)

    def get_night_payloads(self, date_str: Optional[str] = None) -> List[Dict]:
        target_date = date_str or self._today()
        return self._build_payloads_for_date(target_date, "night")
