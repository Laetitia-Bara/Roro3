"""Persistent merchant configuration and fail-closed monitoring selection."""

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest

from roro3.merchants import MerchantService
from roro3.models import Merchant, Offer, RunPolicy, ScheduleWindow
from roro3.observations import MonitorService
from roro3.reservations import ReservationService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)
MANUAL = ScheduleWindow(1, time(18), time(18, 15))
ESTIMATED = ScheduleWindow(1, time(18, 15), time(18, 30), "estimated", 3)


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    return Repository(tmp_path / "merchants.sqlite3")


def offer_for(merchant_id: str) -> Offer:
    return Offer(
        "invented-bag", merchant_id, NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2, 499
    )


def test_create_edit_and_flags_survive_reopening(repo: Repository) -> None:
    service = MerchantService(repo)
    first = service.create("  Commerce inventé  ", (MANUAL,))
    second = service.create("Autre commerce")
    assert first.id != second.id
    assert first.name == "Commerce inventé"
    assert first.active is True and first.watched is True
    service.set_watched(first.id, False)
    service.set_active(first.id, False)
    edited = service.update(first.id, "Nouveau nom", (replace(MANUAL, weekday=3),))
    reopened = MerchantService(Repository(repo.path))
    assert reopened.get(first.id) == edited
    assert edited.name == "Nouveau nom"
    assert edited.active is False and edited.watched is False
    assert edited.windows == (replace(MANUAL, weekday=3),)


def test_manual_edit_preserves_estimated_windows_and_history(repo: Repository) -> None:
    merchant = Merchant("shop", "Commerce inventé", (MANUAL, ESTIMATED), False, False)
    repo.upsert_merchant(merchant)
    repo.record_observation(offer_for(merchant.id), NOW)
    before_history = repo.list_observations()
    service = MerchantService(repo)
    revised = ScheduleWindow(4, time(17), time(17, 15))
    edited = service.update(merchant.id, "Nouveau nom", (revised,))
    assert set(edited.windows) == {revised, ESTIMATED}
    assert edited.active is False and edited.watched is False
    assert repo.list_observations() == before_history


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_name_never_creates_partial_merchant(repo: Repository, name: str) -> None:
    with pytest.raises(ValueError):
        MerchantService(repo).create(name, (MANUAL,))
    assert repo.list_merchants() == []


@pytest.mark.parametrize("weekday", [-1, 7, 1.5, True])
def test_window_weekday_is_a_valid_integer(weekday) -> None:
    with pytest.raises(ValueError):
        ScheduleWindow(weekday, time(18), time(18, 15))


@pytest.mark.parametrize(
    "start,end",
    [
        (time(18), time(18)),
        (time(18, 15), time(18)),
        (time(23), time(1)),
        (time(18, tzinfo=UTC), time(18, 15)),
        (time(18), time(18, 15, tzinfo=UTC)),
    ],
)
def test_invalid_window_time_rejected(start: time, end: time) -> None:
    with pytest.raises(ValueError):
        ScheduleWindow(1, start, end)


@pytest.mark.parametrize(
    "invalid_windows",
    [
        (MANUAL, MANUAL),
        (MANUAL, ScheduleWindow(1, time(18, 10), time(18, 30))),
        (ESTIMATED,),
    ],
)
def test_invalid_manual_window_set_rolls_back_entire_edit(
    repo: Repository, invalid_windows: tuple[ScheduleWindow, ...]
) -> None:
    merchant = Merchant("shop", "Avant", (MANUAL, ESTIMATED), False, False)
    repo.upsert_merchant(merchant)
    with pytest.raises(ValueError):
        MerchantService(repo).update(
            merchant.id, "Nom qui ne doit pas être enregistré", invalid_windows
        )
    assert Repository(repo.path).get_merchant(merchant.id) == merchant


def test_adjacent_windows_and_same_times_on_other_days_are_valid(repo: Repository) -> None:
    windows = (
        MANUAL,
        ScheduleWindow(1, time(18, 15), time(18, 30)),
        ScheduleWindow(3, time(18), time(18, 15)),
    )
    created = MerchantService(repo).create("Créneaux distincts", windows)
    assert set(created.windows) == set(windows)


def test_updating_unknown_merchant_does_not_silently_create_it(repo: Repository) -> None:
    service = MerchantService(repo)
    for action in (
        lambda: service.get("missing"),
        lambda: service.update("missing", "Nouveau", (MANUAL,)),
        lambda: service.set_active("missing", False),
        lambda: service.set_watched("missing", False),
        lambda: service.refresh_estimates("missing"),
    ):
        with pytest.raises(ValueError):
            action()
    assert repo.list_merchants() == []


def test_merchant_changes_preserve_stop_and_runtime_policy(repo: Repository) -> None:
    policy = RunPolicy(False, True, True, False)
    repo.set_policy(policy)
    repo.set_stopped(True)
    service = MerchantService(repo)
    merchant = service.create("Commerce inventé", (MANUAL,))
    service.set_active(merchant.id, False)
    service.set_watched(merchant.id, False)
    service.update(merchant.id, "Nom modifié", ())
    service.refresh_estimates(merchant.id)
    assert repo.get_policy() == policy
    assert repo.is_stopped() is True
    assert repo.list_attempts() == []
    assert repo.list_observations() == []


def test_refresh_estimates_replaces_only_derived_windows(repo: Repository) -> None:
    merchant = Merchant("shop", "Commerce inventé", (MANUAL, ESTIMATED), False, False)
    repo.upsert_merchant(merchant)
    for day in (6, 13, 20):
        detected = datetime(2026, 10, day, 16, 8, tzinfo=UTC)
        offer = replace(
            offer_for(merchant.id),
            id=f"history-{day}",
            pickup_start=detected + timedelta(hours=1),
            pickup_end=detected + timedelta(hours=2),
        )
        repo.record_observation(replace(offer, available=0), detected - timedelta(minutes=5))
        repo.record_observation(offer, detected)
    refreshed = MerchantService(repo).refresh_estimates(merchant.id)
    expected = ScheduleWindow(1, time(18), time(18, 15), "estimated", 3)
    assert set(refreshed.windows) == {MANUAL, expected}
    assert refreshed.active is False and refreshed.watched is False
    assert len(repo.list_observations()) == 6


@pytest.mark.parametrize(
    "active,watched,outcome",
    [
        (False, True, "merchant_disabled"),
        (True, False, "not_watched"),
        (False, False, "merchant_disabled"),
    ],
)
def test_unselected_merchant_produces_no_monitor_trace_or_action(
    repo: Repository, active: bool, watched: bool, outcome: str
) -> None:
    merchant = Merchant("shop", "Commerce inventé", (), active, watched)
    repo.upsert_merchant(merchant)
    repo.set_policy(RunPolicy(True, True, True, False))
    offer = offer_for(merchant.id)
    connector, notifier = SimulatedConnector([offer]), MemoryNotifier()
    result = MonitorService(repo, connector, notifier).run_once(NOW)
    assert result.observations == result.notifications == 0
    assert result.reservations == ()
    assert connector.reserve_calls == []
    assert notifier.messages == []
    assert repo.list_observations() == repo.list_attempts() == []
    direct = ReservationService(repo, connector).try_reserve(offer, NOW)
    assert direct.outcome == outcome
    assert connector.reserve_calls == []


def test_unknown_merchant_is_rejected_by_monitor_and_direct_action(repo: Repository) -> None:
    repo.set_policy(RunPolicy(True, True, True, False))
    offer = offer_for("unknown")
    connector, notifier = SimulatedConnector([offer]), MemoryNotifier()
    result = MonitorService(repo, connector, notifier).run_once(NOW)
    assert result.observations == result.notifications == 0
    assert result.reservations == ()
    assert repo.list_observations() == repo.list_attempts() == []
    assert ReservationService(repo, connector).try_reserve(offer, NOW).outcome == "unknown_merchant"
    assert connector.reserve_calls == notifier.messages == []


@pytest.mark.parametrize("field", ["active", "watched"])
def test_selection_is_rechecked_at_reservation_boundary(repo: Repository, field: str) -> None:
    merchant = Merchant("shop", "Commerce inventé")
    repo.upsert_merchant(merchant)
    repo.set_policy(RunPolicy(True, True, True, False))
    offer = offer_for(merchant.id)
    connector = SimulatedConnector([offer])
    service = ReservationService(repo, connector)
    another = MerchantService(Repository(repo.path))
    if field == "active":
        another.set_active(merchant.id, False)
    else:
        another.set_watched(merchant.id, False)
    assert service.try_reserve(offer, NOW).outcome in {"merchant_disabled", "not_watched"}
    assert connector.reserve_calls == []
    assert repo.list_attempts() == []


def test_selection_does_not_prevent_history_consultation_or_erase_attempts(
    repo: Repository,
) -> None:
    merchant = Merchant("shop", "Commerce inventé")
    repo.upsert_merchant(merchant)
    offer = offer_for(merchant.id)
    repo.set_policy(RunPolicy(True, True, True, False))
    connector, notifier = SimulatedConnector([offer]), MemoryNotifier()
    MonitorService(repo, connector, notifier).run_once(NOW)
    history, attempts = repo.list_observations(), repo.list_attempts()
    service = MerchantService(repo)
    service.set_watched(merchant.id, False)
    service.set_active(merchant.id, False)
    assert repo.list_observations() == history
    assert repo.list_attempts() == attempts
    service.set_active(merchant.id, True)
    assert service.get(merchant.id).watched is False


def test_version_one_database_migrates_without_losing_data(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v1.sqlite3"
    windows = json.dumps(
        [
            {
                "weekday": 1,
                "start": "18:00:00",
                "end": "18:15:00",
                "source": "manual",
                "sample_count": 0,
            }
        ]
    )
    # Deliberately build the old schema instead of importing today's schema constant.
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE runtime (id INTEGER PRIMARY KEY, observe INTEGER NOT NULL,
                notify INTEGER NOT NULL, reserve INTEGER NOT NULL, dry_run INTEGER NOT NULL,
                stopped INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE merchants (id TEXT PRIMARY KEY, name TEXT NOT NULL, windows TEXT NOT NULL);
            CREATE TABLE observations (id INTEGER PRIMARY KEY, offer_id TEXT NOT NULL,
                merchant_id TEXT NOT NULL, pickup_start TEXT NOT NULL, observed_at TEXT NOT NULL,
                available INTEGER NOT NULL, event TEXT NOT NULL,
                UNIQUE(offer_id,pickup_start,observed_at));
            CREATE TABLE attempts (id TEXT PRIMARY KEY, account TEXT NOT NULL,
                offer_id TEXT NOT NULL, pickup_start TEXT NOT NULL, kind TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                reference TEXT, UNIQUE(account,offer_id,pickup_start,kind));
            INSERT INTO runtime VALUES(1,0,1,1,1,1);
            INSERT INTO observations VALUES(1,'old-offer','shop','2026-10-27T13:00:00+00:00',
                '2026-10-27T12:00:00+00:00',2,'first_seen_available');
            INSERT INTO attempts VALUES('old-attempt','demo-family','old-offer',
                '2026-10-27T13:00:00+00:00','preview','preview',
                '2026-10-27T12:00:00+00:00','2026-10-27T12:00:00+00:00',NULL);
            PRAGMA user_version=1;
        """)
        db.execute("INSERT INTO merchants VALUES(?,?,?)", ("shop", "Commerce ancien", windows))
    migrated = Repository(path)
    merchant = migrated.get_merchant("shop")
    assert merchant == Merchant("shop", "Commerce ancien", (MANUAL,), True, True)
    assert migrated.get_policy() == RunPolicy(False, True, True, True)
    assert migrated.is_stopped() is True
    assert migrated.list_observations()[0]["offer_id"] == "old-offer"
    assert migrated.list_attempts()[0]["id"] == "old-attempt"
    reopened = Repository(path)
    assert reopened.list_merchants() == migrated.list_merchants()
    assert reopened.list_observations() == migrated.list_observations()
    assert reopened.list_attempts() == migrated.list_attempts()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4


def test_future_database_version_is_not_silently_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
        db.execute("CREATE TABLE marker (value TEXT)")
        db.execute("INSERT INTO marker VALUES('preserve')")
    with pytest.raises(ValueError):
        Repository(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99
        assert db.execute("SELECT value FROM marker").fetchone()[0] == "preserve"
