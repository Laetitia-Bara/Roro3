"""Calcul de créneaux locaux ; aucun minuteur ni connexion cachée."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from roro3.models import ScheduleWindow, utc


def _bounds(window: ScheduleWindow, day: date, zone: ZoneInfo) -> tuple[datetime, datetime] | None:
    if day.weekday() != window.weekday:
        return None
    start = datetime.combine(day, window.start, zone)
    end = datetime.combine(day, window.end, zone)
    if any(
        endpoint.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        != endpoint.replace(tzinfo=None)
        for endpoint in (start, end)
    ):
        return None
    return start.astimezone(UTC), end.astimezone(UTC)


def in_window(
    windows: Iterable[ScheduleWindow], now: datetime, tz_name: str = "Europe/Paris"
) -> bool:
    """Union des créneaux semi-ouverts, comparés en UTC même lors d'un fold."""
    current, zone = utc(now), ZoneInfo(tz_name)
    day = current.astimezone(zone).date()
    return any(
        (bounds := _bounds(window, day, zone)) is not None and bounds[0] <= current < bounds[1]
        for window in windows
    )


def next_window(
    windows: Iterable[ScheduleWindow], now: datetime, tz_name: str = "Europe/Paris"
) -> datetime | None:
    """Première ouverture future ; dans une fenêtre courante, retourner maintenant.

    Heure inexistante au printemps : ignorer cette occurrence. Heure répétée en
    automne : prendre la première occurrence seulement (fold=0), sans double tâche.
    """
    current, zone = utc(now), ZoneInfo(tz_name)
    local_day = current.astimezone(zone).date()
    candidates = []
    for window in windows:
        for offset in range(8):
            day = local_day + timedelta(days=offset)
            bounds = _bounds(window, day, zone)
            if bounds is None:
                continue
            start, end = bounds
            if end <= current:
                continue
            candidates.append(max(current, start))
    return min(candidates).astimezone(zone) if candidates else None
