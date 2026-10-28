"""Un contrôle planifié observe seulement, même si les modes manuels autorisent plus."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from roro3.models import Merchant, Offer, RunPolicy
from roro3.observations import MonitorService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 28, 17, tzinfo=UTC)


class CountingConnector(SimulatedConnector):
    def __init__(self, offers=()):
        super().__init__(offers)
        self.get_calls = 0

    def get_offers(self):
        self.get_calls += 1
        return super().get_offers()


def offer(identifier: str) -> Offer:
    return Offer(
        f"bag-{identifier}",
        identifier,
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=2),
        2,
        499,
    )


def test_observation_only_never_notifies_or_reserves_with_manual_modes_enabled(tmp_path: Path):
    repo = Repository(tmp_path / "observation.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))
    repo.set_policy(RunPolicy(True, True, True, False))
    connector, notifier = CountingConnector([offer("shop")]), MemoryNotifier()

    result = MonitorService(repo, connector, notifier).run_once(
        NOW,
        merchant_ids={"shop"},
        observation_only=True,
    )

    assert result.observations == 1
    assert result.notifications == 0
    assert result.reservations == ()
    assert connector.get_calls == 1
    assert connector.reserve_calls == notifier.messages == repo.list_attempts() == []
    assert repo.get_policy() == RunPolicy(True, True, True, False)


def test_due_subset_excludes_other_available_merchants(tmp_path: Path):
    repo = Repository(tmp_path / "subset.sqlite3")
    for identifier in ("due", "later"):
        repo.upsert_merchant(Merchant(identifier, f"Commerce fictif {identifier}"))
    connector = CountingConnector([offer("due"), offer("later")])

    result = MonitorService(repo, connector, MemoryNotifier()).run_once(
        NOW,
        merchant_ids={"due"},
        observation_only=True,
    )

    assert result.observations == 1
    assert {row["merchant_id"] for row in repo.list_observations()} == {"due"}
    assert connector.reserve_calls == []


def test_empty_due_subset_does_not_read_the_connector(tmp_path: Path):
    repo = Repository(tmp_path / "empty.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))
    connector = CountingConnector([offer("shop")])

    result = MonitorService(repo, connector, MemoryNotifier()).run_once(
        NOW,
        merchant_ids=set(),
        observation_only=True,
    )

    assert result.observations == 0
    assert connector.get_calls == 0
    assert repo.list_observations() == []


def test_observation_disabled_blocks_scheduled_reads_even_if_other_modes_are_enabled(
    tmp_path: Path,
):
    repo = Repository(tmp_path / "disabled.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))
    repo.set_policy(RunPolicy(False, True, True, False))
    connector = CountingConnector([offer("shop")])

    result = MonitorService(repo, connector, MemoryNotifier()).run_once(
        NOW,
        merchant_ids={"shop"},
        observation_only=True,
    )

    assert result.observations == 0
    assert connector.get_calls == 0
    assert repo.list_attempts() == []


@pytest.mark.parametrize("field", ["active", "watched"])
def test_selection_is_rechecked_after_offers_were_read(tmp_path: Path, field: str):
    repo = Repository(tmp_path / "selection.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))

    class SelectionChangedConnector(CountingConnector):
        def get_offers(self):
            if field == "active":
                repo.set_merchant_active("shop", False)
            else:
                repo.set_merchant_watched("shop", False)
            return super().get_offers()

    connector = SelectionChangedConnector([offer("shop")])
    result = MonitorService(repo, connector, MemoryNotifier()).run_once(
        NOW,
        merchant_ids={"shop"},
        observation_only=True,
    )

    assert result.observations == 0
    assert repo.list_observations() == repo.list_attempts() == []
    assert connector.reserve_calls == []


def test_global_stop_received_during_offer_read_prevents_observation(tmp_path: Path):
    repo = Repository(tmp_path / "stop.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))

    class StopConnector(CountingConnector):
        def get_offers(self):
            repo.set_stopped(True)
            return super().get_offers()

    result = MonitorService(repo, StopConnector([offer("shop")]), MemoryNotifier()).run_once(
        NOW,
        merchant_ids={"shop"},
        observation_only=True,
    )

    assert result.stopped
    assert repo.list_observations() == repo.list_attempts() == []


def test_observation_policy_is_rechecked_after_offers_were_read(tmp_path: Path):
    repo = Repository(tmp_path / "policy.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))
    repo.set_policy(RunPolicy(True, True, True, False))

    class PolicyChangedConnector(CountingConnector):
        def get_offers(self):
            repo.set_policy(RunPolicy(False, True, True, False))
            return super().get_offers()

    connector, notifier = PolicyChangedConnector([offer("shop")]), MemoryNotifier()
    result = MonitorService(repo, connector, notifier).run_once(
        NOW,
        merchant_ids={"shop"},
        observation_only=True,
    )

    assert result.observations == result.notifications == 0
    assert connector.reserve_calls == notifier.messages == []
    assert repo.list_observations() == repo.list_attempts() == []


def test_manual_cycle_keeps_its_explicit_reservation_behaviour(tmp_path: Path):
    repo = Repository(tmp_path / "manual.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif"))
    repo.set_policy(RunPolicy(True, True, True, False))
    connector, notifier = CountingConnector([offer("shop")]), MemoryNotifier()

    result = MonitorService(repo, connector, notifier).run_once(NOW)

    assert result.observations == 1
    assert any(item.outcome == "confirmed" for item in result.reservations)
    assert len(connector.reserve_calls) == 1
