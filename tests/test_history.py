from dataclasses import replace
from datetime import UTC, datetime, time, timedelta

from roro3.models import Merchant, Offer, RunPolicy, ScheduleWindow
from roro3.observations import MonitorService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 27, 17, tzinfo=UTC)


def test_merchants_and_observation_transitions_survive_restart(tmp_path):
    path = tmp_path / "history.sqlite3"
    repo = Repository(path)
    merchant = Merchant(
        "shop",
        "Commerce fictif",
        (
            ScheduleWindow(1, time(18), time(18, 15)),
            ScheduleWindow(1, time(18, 15), time(18, 30), "estimated", 3),
        ),
    )
    repo.upsert_merchant(merchant)
    offer = Offer("bag", "shop", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 0)
    assert repo.record_observation(offer, NOW) == "unavailable"
    assert repo.record_observation(replace(offer, available=2), NOW + timedelta(minutes=1)) == (
        "became_available"
    )
    assert repo.record_observation(replace(offer, available=1), NOW + timedelta(minutes=2)) == (
        "still_available"
    )
    reopened = Repository(path)
    assert reopened.list_merchants() == [merchant]
    assert len(reopened.list_observations()) == 3
    assert reopened.record_observation(offer, NOW) == "duplicate"


def test_notifications_deduplicate_an_available_episode(tmp_path):
    repo = Repository(tmp_path / "history.sqlite3")
    repo.set_policy(RunPolicy(observe=False, notify=True))
    offer = Offer("bag", "shop", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2)
    connector, notifier = SimulatedConnector([offer]), MemoryNotifier()
    monitor = MonitorService(repo, connector, notifier)
    assert monitor.run_once(NOW).notifications == 1
    assert monitor.run_once(NOW + timedelta(minutes=1)).notifications == 0
    assert len(notifier.messages) == 1
    assert "SIMULATION" in notifier.messages[0]
    assert connector.reserve_calls == []
    assert len(repo.list_observations()) == 2


def test_stop_prevents_even_connector_reads(tmp_path):
    class NoReadConnector(SimulatedConnector):
        def get_offers(self):
            raise AssertionError("Aucun contrôle attendu après arrêt")

    repo = Repository(tmp_path / "history.sqlite3")
    repo.set_stopped(True)
    result = MonitorService(repo, NoReadConnector(), MemoryNotifier()).run_once(NOW)
    assert result.stopped
    assert repo.list_observations() == []


def test_all_disabled_prevents_even_connector_reads(tmp_path):
    class NoReadConnector(SimulatedConnector):
        def get_offers(self):
            raise AssertionError("Tous les modes sont désactivés")

    repo = Repository(tmp_path / "history.sqlite3")
    repo.set_policy(RunPolicy(False, False, False))
    result = MonitorService(repo, NoReadConnector(), MemoryNotifier()).run_once(NOW)
    assert result.observations == 0
