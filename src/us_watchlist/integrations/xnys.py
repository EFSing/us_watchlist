"""Exchange-calendar adapter for US regular sessions."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from us_watchlist.domain.models import SessionKind, SessionWindow, require_utc

NEW_YORK = "America/New_York"


def _calendar():
    from exchange_calendars import get_calendar

    return get_calendar("XNYS")


def regular_windows(target: date, sessions: int) -> tuple[SessionWindow, ...]:
    calendar = _calendar()
    if not calendar.is_session(target.isoformat()):
        raise ValueError(f"NOT_XNYS_SESSION {target}")
    return tuple(
        SessionWindow(label.date(), SessionKind.REGULAR, calendar.session_open(label).to_pydatetime(),
                      calendar.session_close(label).to_pydatetime())
        for label in calendar.sessions_window(target.isoformat(), -sessions)
    )


def calendar_source() -> str:
    from exchange_calendars import __version__

    return f"XNYS exchange-calendars {__version__}"


def completed_session(now: datetime) -> date:
    require_utc(now)
    calendar = _calendar()
    day = calendar.date_to_session(now.date().isoformat(), direction="previous")
    if calendar.session_close(day) >= now:
        day = calendar.previous_session(day)
    return day.date()


def is_session(day: date) -> bool:
    return bool(_calendar().is_session(day.isoformat()))


def next_session(day: date) -> date:
    return _calendar().next_session(day.isoformat()).date()


def sessions_between(first: date, last: date) -> tuple[date, ...]:
    calendar = _calendar()
    if not calendar.is_session(first.isoformat()) or not calendar.is_session(last.isoformat()) or first > last:
        raise ValueError("PAPER_REQUIRES_ORDERED_XNYS_SESSIONS")
    return tuple(label.date() for label in calendar.sessions_in_range(first.isoformat(), last.isoformat()))


def new_york_date(now: datetime) -> date:
    require_utc(now)
    return now.astimezone(ZoneInfo(NEW_YORK)).date()


def new_york_wall_time(day: date, local_time: time) -> datetime:
    return datetime.combine(day, local_time, tzinfo=ZoneInfo(NEW_YORK))
