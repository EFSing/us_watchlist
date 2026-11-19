"""Exchange-calendar adapter for US regular sessions."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from us_watchlist.domain.models import SessionKind, SessionWindow, require_utc


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


def new_york_date(now: datetime) -> date:
    require_utc(now)
    return now.astimezone(ZoneInfo("America/New_York")).date()
