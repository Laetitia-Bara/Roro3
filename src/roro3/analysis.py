"""Première estimation descriptive, sans prétendre dater une publication."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, time
from zoneinfo import ZoneInfo

from roro3.models import ScheduleWindow


def estimate_windows(
    observations: Iterable[Mapping],
    merchant_id: str,
    min_days: int = 3,
    timezone: str = "Europe/Paris",
) -> tuple[ScheduleWindow, ...]:
    """Compter des jours distincts avec une transition observée, par quart d'heure.

    Pas de probabilité calculée : la couverture des autres jours n'est pas encore modélisée.
    Une première présence sans absence antérieure ne constitue pas une transition.
    """
    if min_days < 1:
        raise ValueError("Le nombre minimal de journées doit être positif")
    buckets: dict[tuple[int, int], set] = defaultdict(set)
    for row in observations:
        if row["merchant_id"] != merchant_id or row["event"] != "became_available":
            continue
        instant = datetime.fromisoformat(row["observed_at"]).astimezone(ZoneInfo(timezone))
        minute = instant.hour * 60 + instant.minute
        buckets[(instant.weekday(), minute // 15 * 15)].add(instant.date())
    windows = []
    for (weekday, minute), days in sorted(buckets.items()):
        if len(days) < min_days or minute + 15 >= 24 * 60:
            continue
        windows.append(
            ScheduleWindow(
                weekday,
                time(minute // 60, minute % 60),
                time((minute + 15) // 60, (minute + 15) % 60),
                "estimated",
                len(days),
            )
        )
    return tuple(windows)
