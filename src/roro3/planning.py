"""Calcul de créneaux locaux ; aucun minuteur ni connexion cachée."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from roro3.models import ScheduleWindow, utc


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
            if day.weekday() != window.weekday:
                continue
            start = datetime.combine(day, window.start, zone)
            end = datetime.combine(day, window.end, zone)
            if any(
                endpoint.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
                != endpoint.replace(tzinfo=None)
                for endpoint in (start, end)
            ):
                continue
            if end.astimezone(UTC) <= current:
                continue
            candidates.append(max(current, start.astimezone(UTC)))
    return min(candidates).astimezone(zone) if candidates else None
