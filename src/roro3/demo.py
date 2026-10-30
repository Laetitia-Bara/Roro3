"""Jeu de démonstration entièrement fictif et reproductible."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from roro3.analysis import estimate_windows
from roro3.models import Merchant, Offer, RunPolicy, ScheduleWindow, utc
from roro3.observations import MonitorService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

DEMO_NOW = datetime(2026, 10, 27, 17, 0, tzinfo=UTC)

# Conserver les identifiants de la première démonstration lors de son évolution.
_CATALOG = {
    "demo-bakery": ("demo-offer-1", 2, 499),
    "demo-garden": ("demo-offer-2", 1, 399),
    "demo-counter": ("demo-offer-3", 0, 599),
}


def demo_offers(repository: Repository, anchor: datetime) -> tuple[Offer, ...]:
    """Catalogue recalculé à la demande, identités et retraits stables pour un même jour.

    Réutiliser une occurrence déjà connue conserve la continuité avec le premier jalon.
    Une création, un renommage ou le tri de la liste ne change jamais les paniers voisins.
    """
    zone = ZoneInfo("Europe/Paris")
    day = utc(anchor).astimezone(zone).date()
    default_pickup = datetime.combine(day, time(20), zone).astimezone(UTC)
    known_pickups: dict[str, datetime] = {}
    for row in repository.list_observations() + repository.list_attempts():
        start = datetime.fromisoformat(row["pickup_start"])
        if start.astimezone(zone).date() == day:
            known_pickups.setdefault(row["offer_id"], start)
    offers = []
    for merchant in repository.list_merchants():
        offer_id, available, price = _CATALOG.get(
            merchant.id, (f"demo-offer-{merchant.id}", 1, 499)
        )
        pickup = known_pickups.get(offer_id, default_pickup)
        offers.append(
            Offer(offer_id, merchant.id, pickup, pickup + timedelta(hours=1), available, price)
        )
    return tuple(offers)


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
    clock: Callable[[], datetime] | None = None,
) -> DemoApp:
    anchor = now or DEMO_NOW
    repo = Repository(database_path, initial_policy, dataset_kind="simulated")
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
    connector = SimulatedConnector(
        offer_source=lambda: demo_offers(repo, clock() if clock else anchor)
    )
    notifier = MemoryNotifier()
    return DemoApp(repo, connector, notifier, MonitorService(repo, connector, notifier))
