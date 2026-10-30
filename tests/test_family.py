"""Bases séparées et observations familiales : aucun connecteur ni commande."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from roro3.demo import build_demo
from roro3.family_ui import parse_quantity
from roro3.history import HistoryFilters, HistoryService
from roro3.models import Merchant, Offer, RunPolicy
from roro3.observations import MonitorService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 30, 17, tzinfo=UTC)


def test_family_recording_is_persistent_and_never_becomes_a_simulated_order(tmp_path):
    path = tmp_path / "family.sqlite3"
    repo = Repository(path, dataset_kind="family")
    repo.upsert_merchant(Merchant("shop", "Commerce local"))
    assert repo.list_observations() == []
    assert repo.record_manual_observation("shop", 0, NOW, "Europe/Paris") == "unavailable"
    assert (
        repo.record_manual_observation("shop", 2, NOW + timedelta(minutes=1), "Europe/Paris")
        == "became_available"
    )
    assert (
        repo.record_manual_observation("shop", 1, NOW + timedelta(minutes=2), "Europe/Paris")
        == "still_available"
    )
    assert (
        repo.record_manual_observation("shop", 1, NOW + timedelta(minutes=2), "Europe/Paris")
        == "duplicate"
    )
    reopened = Repository(path, dataset_kind="family")
    assert len(reopened.list_observations()) == 3
    assert reopened.get_policy() == RunPolicy(observe=False)
    # Même une mauvaise configuration ne peut faire passer la frontière d'action.
    reopened.set_policy(RunPolicy(reserve=True, dry_run=False, notify=True))
    offer = Offer("bag", "shop", NOW, NOW + timedelta(hours=1), 2)
    assert reopened.claim_attempt(offer, "account", NOW).outcome == "disabled"

    class NoReads(SimulatedConnector):
        def get_offers(self):
            raise AssertionError("Une base familiale ne lit jamais le simulateur")

    notifier = MemoryNotifier()
    assert MonitorService(reopened, NoReads(), notifier).run_once(NOW).observations == 0
    assert reopened.list_attempts() == []
    assert notifier.messages == []


def test_demo_and_family_cannot_share_a_database(tmp_path):
    demo = build_demo(tmp_path / "demo.sqlite3")
    before = demo.repo.list_observations()
    with pytest.raises(ValueError, match="autre mode"):
        Repository(demo.repo.path, dataset_kind="family")
    assert demo.repo.list_observations() == before
    family = Repository(tmp_path / "family.sqlite3", dataset_kind="family")
    with pytest.raises(ValueError, match="autre mode"):
        build_demo(family.path)
    assert family.list_merchants() == []
    assert family.list_observations() == []


def test_migration_from_schema_three_preserves_every_business_row(tmp_path):
    repo = build_demo(tmp_path / "old.sqlite3").repo
    repo.set_stopped(True)
    before = (repo.list_merchants(), repo.list_observations(), repo.get_policy())
    with repo.connection() as db:
        db.execute("DROP TABLE dataset")
        db.execute("PRAGMA user_version=3")
    updated = Repository(repo.path)
    assert updated.dataset_kind == "simulated"
    assert (updated.list_merchants(), updated.list_observations(), updated.get_policy()) == before
    assert updated.is_stopped()
    with updated.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4


def test_manual_first_presence_is_not_a_transition_and_days_do_not_leak(tmp_path):
    repo = Repository(tmp_path / "family.sqlite3", dataset_kind="family")
    repo.upsert_merchant(Merchant("shop", "Commerce local"))
    assert repo.record_manual_observation("shop", 2, NOW, "Europe/Paris") == "first_seen_available"
    assert (
        repo.record_manual_observation("shop", 0, NOW + timedelta(minutes=1), "Europe/Paris")
        == "unavailable"
    )
    tomorrow = NOW + timedelta(days=1)
    assert (
        repo.record_manual_observation("shop", 1, tomorrow, "Europe/Paris")
        == "first_seen_available"
    )
    assert HistoryService(repo).query(HistoryFilters("shop")).patterns == ()


def test_manual_validation_and_stop_leave_no_partial_record(tmp_path):
    repo = Repository(tmp_path / "family.sqlite3", dataset_kind="family")
    repo.upsert_merchant(Merchant("shop", "Commerce local"))
    for key, quantity in (("unknown", 1), ("shop", -1), ("shop", True), ("shop", 1.5)):
        with pytest.raises(ValueError):
            repo.record_manual_observation(key, quantity, NOW, "Europe/Paris")
    repo.set_stopped(True)
    with pytest.raises(ValueError, match="arrêté"):
        repo.record_manual_observation("shop", 1, NOW, "Europe/Paris")
    repo.set_stopped(False)
    repo.upsert_merchant(replace(repo.get_merchant("shop"), active=False))
    with pytest.raises(ValueError, match="Réactivez"):
        repo.record_manual_observation("shop", 1, NOW, "Europe/Paris")
    assert repo.list_observations() == []


@pytest.mark.parametrize("value", [None, True, -1, 1.5, 1001, float("nan"), float("inf")])
def test_mobile_quantity_validation(value):
    with pytest.raises(ValueError):
        parse_quantity(value)


def test_manual_record_rejects_clock_reversal(tmp_path):
    repo = Repository(tmp_path / "family.sqlite3", dataset_kind="family")
    repo.upsert_merchant(Merchant("shop", "Commerce local"))
    repo.record_manual_observation("shop", 0, NOW, "Europe/Paris")
    with pytest.raises(ValueError, match="horloge"):
        repo.record_manual_observation("shop", 2, NOW - timedelta(seconds=1), "Europe/Paris")
    assert len(repo.list_observations()) == 1
