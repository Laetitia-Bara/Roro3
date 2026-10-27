"""Safety invariants for the simulated reservation boundary.

These tests use only invented offers and a temporary SQLite database. A
reservation call is observable even when the connector itself is simulated:
notification-only operation and dry-run must never invoke that method.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from threading import Barrier

import pytest

from roro3.models import AttemptStatus, Offer, RunPolicy
from roro3.observations import MonitorService
from roro3.ports import ReservationRejected
from roro3.reservations import ReservationService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
def offer() -> Offer:
    return Offer(
        id="demo-offer",
        merchant_id="demo-bakery",
        pickup_start=datetime(2026, 10, 27, 17, 0, tzinfo=UTC),
        pickup_end=datetime(2026, 10, 27, 18, 0, tzinfo=UTC),
        available=2,
        price_minor=450,
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "reservations.sqlite3"


def automatic_policy() -> RunPolicy:
    return RunPolicy(observe=True, notify=True, reserve=True, dry_run=False)


@pytest.mark.parametrize("observe,notify,dry_run", list(product((False, True), repeat=3)))
def test_non_reserving_policies_never_call_reserve(
    database_path: Path,
    offer: Offer,
    observe: bool,
    notify: bool,
    dry_run: bool,
) -> None:
    repository = Repository(database_path)
    repository.set_policy(RunPolicy(observe=observe, notify=notify, reserve=False, dry_run=dry_run))
    connector = SimulatedConnector([offer])

    result = ReservationService(repository, connector).try_reserve(offer, NOW)

    assert result.outcome == "disabled"
    assert connector.reserve_calls == []
    assert repository.list_attempts() == []


@pytest.mark.parametrize("observe,notify", list(product((False, True), repeat=2)))
def test_dry_run_never_calls_connector_mutation(
    database_path: Path, offer: Offer, observe: bool, notify: bool
) -> None:
    repository = Repository(database_path)
    repository.set_policy(RunPolicy(observe=observe, notify=notify, reserve=True, dry_run=True))
    connector = SimulatedConnector([offer])

    result = ReservationService(repository, connector).try_reserve(offer, NOW)

    assert result.outcome == "preview"
    assert connector.reserve_calls == []
    assert [attempt["status"] for attempt in repository.list_attempts()] == [
        AttemptStatus.PREVIEW.value
    ]


def test_unavailable_offer_cannot_be_reserved(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    unavailable = replace(offer, available=0)
    connector = SimulatedConnector([unavailable])

    result = ReservationService(repository, connector).try_reserve(unavailable, NOW)

    assert result.outcome == "unavailable"
    assert connector.reserve_calls == []
    assert repository.list_attempts() == []


def test_stop_is_read_at_action_boundary(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)

    # A second application component stops an already-created service.
    Repository(database_path).set_stopped(True)
    result = service.try_reserve(offer, NOW)

    assert result.outcome == "stopped"
    assert connector.reserve_calls == []
    assert repository.list_attempts() == []


def test_stop_and_policy_survive_restart(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    repository.set_stopped(True)

    # Initial configuration must not overwrite persisted user choices.
    restarted = Repository(database_path, initial_policy=RunPolicy())
    connector = SimulatedConnector([offer])
    result = ReservationService(restarted, connector).try_reserve(offer, NOW)

    assert restarted.get_policy() == automatic_policy()
    assert restarted.is_stopped() is True
    assert result.outcome == "stopped"
    assert connector.reserve_calls == []


def test_disabled_policy_is_read_after_service_creation(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)

    Repository(database_path).set_policy(RunPolicy(reserve=False, dry_run=False))
    result = service.try_reserve(offer, NOW)

    assert result.outcome == "disabled"
    assert connector.reserve_calls == []


def test_duplicate_is_blocked_after_database_reopening(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])

    first = ReservationService(repository, connector).try_reserve(offer, NOW)
    second = ReservationService(Repository(database_path), connector).try_reserve(
        offer, NOW + timedelta(seconds=1)
    )

    assert first.outcome == "confirmed"
    assert second.outcome == "duplicate"
    assert len(connector.reserve_calls) == 1
    attempts = Repository(database_path).list_attempts()
    assert len(attempts) == 1
    assert attempts[0]["status"] == AttemptStatus.CONFIRMED.value
    assert attempts[0]["reference"] == first.reference


def test_two_services_with_separate_connections_share_one_claim(
    database_path: Path, offer: Offer
) -> None:
    Repository(database_path).set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    start = Barrier(2)

    def reserve_from_separate_repository() -> str:
        service = ReservationService(Repository(database_path), connector)
        start.wait(timeout=5)
        return service.try_reserve(offer, NOW).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve_from_separate_repository) for _ in range(2)]
        outcomes = [future.result(timeout=10) for future in futures]

    assert sorted(outcomes) == ["confirmed", "duplicate"]
    assert len(connector.reserve_calls) == 1
    assert len(Repository(database_path).list_attempts()) == 1


def test_unknown_outcome_stays_blocking_after_restart(database_path: Path, offer: Offer) -> None:
    class LostResponseConnector(SimulatedConnector):
        def reserve(self, selected_offer: Offer) -> str:
            self.reserve_calls.append(selected_offer)
            raise TimeoutError("Fictitious response lost after sending the request")

    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = LostResponseConnector([offer])

    first = ReservationService(repository, connector).try_reserve(offer, NOW)
    second = ReservationService(Repository(database_path), connector).try_reserve(
        offer, NOW + timedelta(minutes=1)
    )

    assert first.outcome == "unknown"
    assert second.outcome == "duplicate"
    assert len(connector.reserve_calls) == 1
    assert Repository(database_path).list_attempts()[0]["status"] == (AttemptStatus.UNKNOWN.value)


def test_explicit_rejection_is_preserved_as_failure(database_path: Path, offer: Offer) -> None:
    class RejectingConnector(SimulatedConnector):
        def reserve(self, selected_offer: Offer) -> str:
            self.reserve_calls.append(selected_offer)
            raise ReservationRejected("Fictitious offer is no longer available")

    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = RejectingConnector([offer])

    result = ReservationService(repository, connector).try_reserve(offer, NOW)

    assert result.outcome == "failed"
    assert result.reference is None
    assert repository.list_attempts()[0]["status"] == AttemptStatus.FAILED.value


def test_preview_is_deduplicated_but_does_not_block_simulated_reservation(
    database_path: Path, offer: Offer
) -> None:
    repository = Repository(database_path)
    repository.set_policy(replace(automatic_policy(), dry_run=True))
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)

    preview = service.try_reserve(offer, NOW)
    service.try_reserve(offer, NOW + timedelta(seconds=1))

    assert preview.outcome == "preview"
    assert connector.reserve_calls == []
    assert len(repository.list_attempts()) == 1

    repository.set_policy(automatic_policy())
    confirmed = service.try_reserve(offer, NOW + timedelta(seconds=2))

    assert confirmed.outcome == "confirmed"
    assert len(connector.reserve_calls) == 1
    assert sorted(attempt["status"] for attempt in repository.list_attempts()) == sorted(
        [AttemptStatus.PREVIEW.value, AttemptStatus.CONFIRMED.value]
    )


def test_same_pickup_in_different_timezones_is_the_same_offer(
    database_path: Path, offer: Offer
) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)
    local_offset = timezone(timedelta(hours=1))
    same_offer = replace(
        offer,
        pickup_start=offer.pickup_start.astimezone(local_offset),
        pickup_end=offer.pickup_end.astimezone(local_offset),
    )

    first = service.try_reserve(offer, NOW)
    second = service.try_reserve(same_offer, NOW)

    assert first.outcome == "confirmed"
    assert second.outcome == "duplicate"
    assert len(connector.reserve_calls) == 1


def test_non_simulated_connector_is_rejected(database_path: Path, offer: Offer) -> None:
    class UnsupportedConnector(SimulatedConnector):
        is_simulated = False

    with pytest.raises(ValueError):
        ReservationService(Repository(database_path), UnsupportedConnector([offer]))


def test_pending_claim_after_crash_prevents_retry(database_path: Path, offer: Offer) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])

    # Reproduce a process disappearing after admission but before recording a result.
    claim = repository.claim_attempt(offer, connector.account_id, NOW)
    assert claim.outcome == "claimed"

    restarted = Repository(database_path)
    result = ReservationService(restarted, connector).try_reserve(offer, NOW + timedelta(seconds=1))

    assert result.outcome == "duplicate"
    assert connector.reserve_calls == []
    attempts = restarted.list_attempts()
    assert len(attempts) == 1
    assert attempts[0]["status"] in {
        AttemptStatus.PENDING.value,
        AttemptStatus.UNKNOWN.value,
    }


@pytest.mark.parametrize("different_key", ["offer", "pickup"])
def test_different_offer_or_pickup_at_same_merchant_is_allowed(
    database_path: Path, offer: Offer, different_key: str
) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)
    if different_key == "offer":
        other_offer = replace(offer, id="another-demo-offer")
    else:
        other_offer = replace(
            offer,
            pickup_start=offer.pickup_start + timedelta(days=1),
            pickup_end=offer.pickup_end + timedelta(days=1),
        )

    first = service.try_reserve(offer, NOW)
    second = service.try_reserve(other_offer, NOW)

    assert first.outcome == second.outcome == "confirmed"
    assert other_offer.merchant_id == offer.merchant_id
    assert len(connector.reserve_calls) == 2
    assert len(repository.list_attempts()) == 2


def test_stop_and_explicit_resume_preserve_previous_attempts(
    database_path: Path, offer: Offer
) -> None:
    repository = Repository(database_path)
    repository.set_policy(automatic_policy())
    connector = SimulatedConnector([offer])
    service = ReservationService(repository, connector)
    first = service.try_reserve(offer, NOW)
    previous_attempts = repository.list_attempts()
    new_offer = replace(offer, id="offer-after-explicit-resume")

    repository.set_stopped(True)
    stopped = service.try_reserve(new_offer, NOW)

    assert stopped.outcome == "stopped"
    assert repository.list_attempts() == previous_attempts
    assert len(connector.reserve_calls) == 1

    repository.set_stopped(False)
    resumed = service.try_reserve(new_offer, NOW)

    assert resumed.outcome == "confirmed"
    assert len(connector.reserve_calls) == 2
    assert any(
        attempt["reference"] == first.reference
        and attempt["status"] == AttemptStatus.CONFIRMED.value
        for attempt in repository.list_attempts()
    )


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("seconds_after_end", [0, 1])
def test_expired_pickup_cannot_be_reserved_or_previewed(
    database_path: Path, offer: Offer, dry_run: bool, seconds_after_end: int
) -> None:
    repository = Repository(database_path)
    repository.set_policy(replace(automatic_policy(), dry_run=dry_run))
    connector = SimulatedConnector([offer])
    expired_now = offer.pickup_end + timedelta(seconds=seconds_after_end)

    result = ReservationService(repository, connector).try_reserve(offer, expired_now)

    assert result.outcome == "unavailable"
    assert connector.reserve_calls == []
    assert repository.list_attempts() == []


def test_observation_without_notifications_does_not_send_messages(
    database_path: Path, offer: Offer
) -> None:
    repository = Repository(database_path)
    repository.set_policy(RunPolicy(observe=True, notify=False, reserve=False, dry_run=False))
    connector = SimulatedConnector([offer])
    notifier = MemoryNotifier()

    result = MonitorService(repository, connector, notifier).run_once(NOW)

    assert result.observations == 1
    assert result.notifications == 0
    assert notifier.messages == []
    assert connector.reserve_calls == []
    assert repository.list_attempts() == []
