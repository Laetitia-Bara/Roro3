"""Jeu de démonstration entièrement fictif et reproductible."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from roro3.analysis import estimate_windows
from roro3.models import Merchant, Offer, RunPolicy, ScheduleWindow
from roro3.observations import MonitorService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

DEMO_NOW = datetime(2026, 10, 27, 17, 0, tzinfo=UTC)


@dataclass(frozen=True)
class DemoApp:
    repo: Repository
    connector: SimulatedConnector
    notifier: MemoryNotifier
    monitor: MonitorService


def build_demo(
    database_path: Path,
    now: datetime | None = None,
    initial_policy: RunPolicy | None = None,
) -> DemoApp:
    anchor = now or DEMO_NOW
    repo = Repository(database_path, initial_policy)
    merchants = (
        Merchant("demo-bakery", "L’Atelier du Pain", (ScheduleWindow(1, time(18), time(18, 15)),)),
        Merchant(
            "demo-garden", "Le Panier des Jardins", (ScheduleWindow(3, time(18, 30), time(18, 45)),)
        ),
        Merchant(
            "demo-counter",
            "Le Comptoir du Quartier",
            (ScheduleWindow(0, time(12, 15), time(12, 30)),),
        ),
    )
    # Initialisation idempotente : ne pas réécrire les choix d'une base existante.
    if not repo.list_merchants():
        for merchant in merchants:
            repo.upsert_merchant(merchant)
        for day in (6, 13, 20):
            detected = datetime(2026, 10, day, 18, 8, tzinfo=ZoneInfo("Europe/Paris"))
            offer = Offer(
                f"history-{day}",
                "demo-bakery",
                detected + timedelta(hours=1),
                detected + timedelta(hours=2),
                2,
                499,
            )
            repo.record_observation(replace(offer, available=0), detected - timedelta(minutes=6))
            repo.record_observation(offer, detected)
        first = merchants[0]
        estimated = estimate_windows(repo.list_observations(), first.id)
        repo.upsert_merchant(replace(first, windows=first.windows + estimated))
    offers = tuple(
        Offer(
            f"demo-offer-{index}",
            merchant.id,
            anchor + timedelta(hours=1),
            anchor + timedelta(hours=2),
            available,
            price,
        )
        for index, (merchant, available, price) in enumerate(
            zip(merchants, (2, 1, 0), (499, 399, 599), strict=True), 1
        )
    )
    connector, notifier = SimulatedConnector(offers), MemoryNotifier()
    return DemoApp(repo, connector, notifier, MonitorService(repo, connector, notifier))
