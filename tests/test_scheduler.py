"""Horloge virtuelle et vraies transactions SQLite, sans attente ni accès réseau."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from roro3.models import Merchant, Offer, RunPolicy, ScheduleWindow
from roro3.observations import MonitorService
from roro3.scheduler import SchedulerService
from roro3.simulator import MemoryNotifier, SimulatedConnector
from roro3.storage import Repository

NOW = datetime(2026, 10, 28, 17, tzinfo=UTC)  # Mercredi 18 h à Paris.
WINDOW = ScheduleWindow(2, time(18), time(18, 5))


class CountingConnector(SimulatedConnector):
    def __init__(self, offers=()):
        super().__init__(offers)
        self.get_calls = 0

    def get_offers(self):
        self.get_calls += 1
        return super().get_offers()


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "scheduler.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce fictif", (WINDOW,)))
    return repo


def make_scheduler(repository: Repository, connector=None):
    connector = connector or CountingConnector(
        [
            Offer("bag", "shop", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2, 499),
        ]
    )
    notifier = MemoryNotifier()
    monitor = MonitorService(repository, connector, notifier)
    return SchedulerService(repository, monitor), connector, notifier


def heartbeat(scheduler: SchedulerService, seconds: range) -> None:
    for elapsed in seconds:
        assert scheduler.tick(NOW + timedelta(seconds=elapsed)) is None


def test_no_cycle_is_started_by_construction(repository: Repository):
    scheduler, connector, notifier = make_scheduler(repository)
    assert not scheduler.status(NOW).running
    assert scheduler.tick(NOW) is None
    assert connector.get_calls == 0
    assert repository.list_observations() == repository.list_attempts() == notifier.messages == []


def test_version_two_migration_preserves_selection_modes_and_history(tmp_path: Path):
    path = tmp_path / "legacy-v2.sqlite3"
    with sqlite3.connect(path) as db:
        # Représenter l'ancien schéma, sans importer le schéma courant à migrer.
        db.executescript("""
            CREATE TABLE runtime (id INTEGER PRIMARY KEY, observe INTEGER NOT NULL,
                notify INTEGER NOT NULL, reserve INTEGER NOT NULL, dry_run INTEGER NOT NULL,
                stopped INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE merchants (id TEXT PRIMARY KEY, name TEXT NOT NULL, windows TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, watched INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE observations (id INTEGER PRIMARY KEY, offer_id TEXT NOT NULL,
                merchant_id TEXT NOT NULL, pickup_start TEXT NOT NULL, observed_at TEXT NOT NULL,
                available INTEGER NOT NULL, event TEXT NOT NULL,
                UNIQUE(offer_id,pickup_start,observed_at));
            CREATE TABLE attempts (id TEXT PRIMARY KEY, account TEXT NOT NULL,
                offer_id TEXT NOT NULL, pickup_start TEXT NOT NULL, kind TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                reference TEXT, UNIQUE(account,offer_id,pickup_start,kind));
            INSERT INTO runtime VALUES(1,1,1,1,0,1);
            INSERT INTO merchants VALUES('old-shop','Ancien commerce fictif','[]',0,0);
            INSERT INTO observations VALUES(1,'old-bag','old-shop','2026-10-28T18:00:00+00:00',
                '2026-10-28T17:00:00+00:00',1,'first_seen_available');
            INSERT INTO attempts VALUES('old-claim','demo-family','old-bag',
                '2026-10-28T18:00:00+00:00','simulation','unknown',
                '2026-10-28T17:00:00+00:00','2026-10-28T17:00:00+00:00',NULL);
            PRAGMA user_version=2;
        """)

    repo = Repository(path)
    assert repo.get_merchant("old-shop") == Merchant(
        "old-shop",
        "Ancien commerce fictif",
        (),
        False,
        False,
    )
    assert repo.get_policy() == RunPolicy(True, True, True, False)
    assert repo.is_stopped()
    assert repo.list_observations()[0]["offer_id"] == "old-bag"
    assert repo.list_attempts()[0]["status"] == "unknown"
    scheduler, connector, _ = make_scheduler(repo)
    assert scheduler.status(NOW).interval_seconds == 60
    assert not scheduler.status(NOW).running
    assert scheduler.tick(NOW) is None
    assert connector.get_calls == 0
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_one_shared_scan_runs_at_cadence_even_when_manual_modes_allow_reservation(
    repository: Repository,
):
    repository.set_policy(RunPolicy(True, True, True, False))
    scheduler, connector, notifier = make_scheduler(repository)
    scheduler.start(NOW)

    first = scheduler.tick(NOW)
    assert first is not None and first.observations == 1
    assert first.notifications == 0 and first.reservations == ()
    assert scheduler.status(NOW + timedelta(seconds=1)).next_check == NOW + timedelta(seconds=60)
    heartbeat(scheduler, range(10, 60, 10))
    assert scheduler.tick(NOW + timedelta(seconds=59)) is None
    second = scheduler.tick(NOW + timedelta(seconds=60))

    assert second is not None and second.observations == 1
    assert connector.get_calls == 2
    assert len(repository.list_observations()) == 2
    assert connector.reserve_calls == notifier.messages == repository.list_attempts() == []
    assert repository.get_policy() == RunPolicy(True, True, True, False)


@pytest.mark.parametrize("offset,observations", [(-1, 0), (0, 1), (300, 0)])
def test_windows_are_half_open(repository: Repository, offset: int, observations: int):
    moment = NOW + timedelta(seconds=offset)
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(moment)
    result = scheduler.tick(moment)
    assert len(repository.list_observations()) == observations
    assert connector.get_calls == int(observations > 0)
    if observations:
        assert result is not None
    else:
        assert result is None


def test_manual_and_estimated_overlap_does_not_duplicate_a_scan(repository: Repository):
    merchant = repository.get_merchant("shop")
    repository.upsert_merchant(
        replace(
            merchant,
            windows=(WINDOW, replace(WINDOW, source="estimated", sample_count=3)),
        )
    )
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    result = scheduler.tick(NOW)
    assert result is not None and result.observations == 1
    assert connector.get_calls == 1
    assert scheduler.tick(NOW) is None
    assert len(repository.list_observations()) == 1


def test_only_due_merchants_are_observed_and_reads_are_shared(repository: Repository):
    repository.upsert_merchant(
        Merchant(
            "later",
            "Commerce fictif suivant",
            (ScheduleWindow(2, time(18, 1), time(18, 5)),),
        )
    )
    offers = [
        Offer(
            f"bag-{identifier}", identifier, NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2
        )
        for identifier in ("shop", "later")
    ]
    scheduler, connector, _ = make_scheduler(repository, CountingConnector(offers))
    scheduler.start(NOW)
    assert scheduler.tick(NOW).observations == 1
    assert {row["merchant_id"] for row in repository.list_observations()} == {"shop"}
    heartbeat(scheduler, range(10, 60, 10))
    assert scheduler.tick(NOW + timedelta(seconds=60)).observations == 2
    assert connector.get_calls == 2
    assert len(repository.list_observations()) == 3


@pytest.mark.parametrize("field", ["active", "watched", "windows"])
def test_editing_selection_or_windows_is_applied_on_next_tick(repository: Repository, field: str):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    merchant = repository.get_merchant("shop")
    update = {field: () if field == "windows" else False}
    Repository(repository.path).upsert_merchant(replace(merchant, **update))

    heartbeat(scheduler, range(10, 60, 10))
    assert scheduler.tick(NOW + timedelta(seconds=60)) is None
    assert connector.get_calls == 1
    assert len(repository.list_observations()) == 1
    assert scheduler.status(NOW + timedelta(seconds=60)).next_check is None


def test_merchant_without_window_is_not_scheduled(repository: Repository):
    repository.upsert_merchant(Merchant("shop", "Sans horaire"))
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    assert scheduler.tick(NOW) is None
    assert scheduler.status(NOW).next_check is None
    assert connector.get_calls == 0


def test_next_check_moves_to_the_next_window_when_cadence_would_exceed_the_end(
    repository: Repository,
):
    repository.upsert_merchant(
        Merchant(
            "shop",
            "Fenêtre courte",
            (ScheduleWindow(2, time(18), time(18, 1)),),
        )
    )
    moment = NOW + timedelta(seconds=45)
    scheduler, _, _ = make_scheduler(repository)
    scheduler.start(moment)
    scheduler.tick(moment)
    next_check = scheduler.status(moment + timedelta(seconds=1)).next_check
    assert next_check == datetime(2026, 11, 4, 17, tzinfo=UTC)


def test_interval_is_persistent_but_a_new_instance_is_not_started(repository: Repository):
    scheduler, _, _ = make_scheduler(repository)
    scheduler.set_interval_seconds(30)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    scheduler.close()

    reopened_repo = Repository(repository.path)
    reopened, connector, _ = make_scheduler(reopened_repo)
    assert reopened.status(NOW + timedelta(seconds=1)).interval_seconds == 30
    assert not reopened.status(NOW + timedelta(seconds=1)).running
    assert reopened.tick(NOW + timedelta(seconds=1)) is None
    assert connector.get_calls == 0


@pytest.mark.parametrize("interval", [0, 14, 3601, True, 30.5, "60"])
def test_invalid_interval_is_rejected_without_changing_the_setting(
    repository: Repository,
    interval,
):
    scheduler, _, _ = make_scheduler(repository)
    with pytest.raises(ValueError):
        scheduler.set_interval_seconds(interval)
    assert scheduler.status(NOW).interval_seconds == 60


def test_expired_lease_requires_explicit_restart(repository: Repository):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)

    assert scheduler.tick(NOW + timedelta(seconds=16)) is None
    assert not scheduler.status(NOW + timedelta(seconds=16)).running
    assert scheduler.tick(NOW + timedelta(seconds=60)) is None
    assert connector.get_calls == 1

    scheduler.start(NOW + timedelta(seconds=60))
    assert scheduler.tick(NOW + timedelta(seconds=60)).observations == 1
    assert connector.get_calls == 2


def test_another_instance_cannot_take_a_live_lease_or_restart_it_by_construction(
    repository: Repository,
):
    owner, first_connector, _ = make_scheduler(repository)
    owner.start(NOW)
    owner.tick(NOW)
    another, second_connector, _ = make_scheduler(Repository(repository.path))
    assert another.status(NOW + timedelta(seconds=1)).running
    assert not another.status(NOW + timedelta(seconds=1)).owned
    assert another.tick(NOW + timedelta(seconds=1)) is None
    with pytest.raises(ValueError):
        another.start(NOW + timedelta(seconds=1))
    another.close()
    assert owner.status(NOW + timedelta(seconds=1)).running
    assert first_connector.get_calls == 1 and second_connector.get_calls == 0


def test_expired_owner_takeover_keeps_the_persisted_cadence(repository: Repository):
    first, first_connector, _ = make_scheduler(repository)
    first.start(NOW)
    first.tick(NOW)
    replacement, second_connector, _ = make_scheduler(Repository(repository.path))

    replacement.start(NOW + timedelta(seconds=16))
    assert replacement.tick(NOW + timedelta(seconds=16)) is None
    assert first.tick(NOW + timedelta(seconds=20)) is None
    assert replacement.status(NOW + timedelta(seconds=16)).next_check == (
        NOW + timedelta(seconds=60)
    )
    heartbeat(replacement, range(26, 60, 10))
    assert replacement.tick(NOW + timedelta(seconds=60)).observations == 1

    assert first_connector.get_calls == second_connector.get_calls == 1
    assert len(repository.list_observations()) == 2


def test_two_concurrent_services_cannot_admit_duplicate_scheduled_work(repository: Repository):
    start = Barrier(2)
    services = [make_scheduler(Repository(repository.path)) for _ in range(2)]

    def activate(item):
        service, _, _ = item
        start.wait(timeout=5)
        try:
            service.start(NOW)
        except ValueError:
            return "blocked"
        service.tick(NOW)
        return "started"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(activate, services))

    assert sorted(results) == ["blocked", "started"]
    assert sum(connector.get_calls for _, connector, _ in services) == 1
    assert len(repository.list_observations()) == 1


def test_global_stop_and_resume_do_not_restart_the_scheduler(repository: Repository):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    Repository(repository.path).set_stopped(True)
    assert scheduler.tick(NOW + timedelta(seconds=1)) is None
    Repository(repository.path).set_stopped(False)
    assert scheduler.tick(NOW + timedelta(seconds=2)) is None
    assert not scheduler.status(NOW + timedelta(seconds=2)).running
    assert connector.get_calls == 1


def test_explicit_stop_blocks_further_checks_and_preserves_history(repository: Repository):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    before = repository.list_observations()
    scheduler.stop()
    assert scheduler.tick(NOW + timedelta(seconds=1)) is None
    assert not scheduler.status(NOW + timedelta(seconds=1)).running
    assert repository.list_observations() == before
    assert connector.get_calls == 1


@pytest.mark.parametrize("global_stop,observe", [(True, True), (False, False)])
def test_start_refuses_an_incompatible_runtime_policy(
    repository: Repository,
    global_stop: bool,
    observe: bool,
):
    repository.set_stopped(global_stop)
    policy = RunPolicy(observe, True, True, False)
    repository.set_policy(policy)
    scheduler, connector, _ = make_scheduler(repository)
    with pytest.raises(ValueError):
        scheduler.start(NOW)
    assert connector.get_calls == 0
    assert repository.get_policy() == policy


def test_disabling_observation_during_a_run_prevents_new_checks(repository: Repository):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    repository.set_policy(RunPolicy(False, True, True, False))
    assert scheduler.tick(NOW + timedelta(seconds=1)) is None
    assert connector.get_calls == 1
    assert repository.list_attempts() == []


def test_observation_off_then_on_between_ticks_does_not_restart_a_session(
    repository: Repository,
):
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    another_view = Repository(repository.path)
    another_view.set_policy(RunPolicy(False, True, True, False))
    another_view.set_policy(RunPolicy(True, True, True, False))

    # Aucun tick n'a eu lieu pendant la désactivation, et le bail n'a pas expiré.
    assert scheduler.tick(NOW + timedelta(seconds=1)) is None
    assert not scheduler.status(NOW + timedelta(seconds=1)).running
    assert connector.get_calls == 1
    assert len(repository.list_observations()) == 1

    scheduler.start(NOW + timedelta(seconds=1))
    assert scheduler.status(NOW + timedelta(seconds=1)).running
    assert scheduler.tick(NOW + timedelta(seconds=1)) is None
    assert repository.get_policy() == RunPolicy(True, True, True, False)


def test_result_from_previous_owner_is_discarded_if_ownership_changes_during_read(
    repository: Repository,
):
    replacement, replacement_connector, _ = make_scheduler(Repository(repository.path))
    transfer = []

    class OwnershipChangedConnector(CountingConnector):
        def get_offers(self):
            original.stop()
            replacement.start(NOW + timedelta(seconds=1))
            transfer.append(True)
            return super().get_offers()

    connector = OwnershipChangedConnector(
        [
            Offer("bag", "shop", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2),
        ]
    )
    original, _, notifier = make_scheduler(repository, connector)
    original.start(NOW)
    result = original.tick(NOW)

    assert transfer == [True]
    assert result is None or result.stopped
    assert repository.list_observations() == repository.list_attempts() == []
    assert connector.reserve_calls == notifier.messages == []
    assert replacement.status(NOW + timedelta(seconds=1)).owned

    # Fermer l'ancienne instance ne doit pas désarmer le nouveau propriétaire.
    original.close()
    assert replacement.status(NOW + timedelta(seconds=1)).running
    assert replacement.tick(NOW + timedelta(seconds=1)) is None
    assert replacement_connector.get_calls == 0  # Cadence déjà réclamée, même sans résultat.


def test_connector_failure_is_sanitized_and_retried_at_the_configured_cadence(
    repository: Repository,
    caplog,
):
    sensitive = "token=fictitious-private-value-do-not-log"

    class FailingOnceConnector(CountingConnector):
        def get_offers(self):
            if not self.get_calls:
                self.get_calls += 1
                raise RuntimeError(sensitive)
            return super().get_offers()

    connector = FailingOnceConnector(
        [
            Offer("bag", "shop", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 2),
        ]
    )
    scheduler, _, _ = make_scheduler(repository, connector)
    scheduler.start(NOW)
    scheduler.tick(NOW)
    error = scheduler.status(NOW).last_error
    assert error and sensitive not in error
    assert sensitive not in caplog.text
    assert connector.get_calls == 1
    heartbeat(scheduler, range(10, 60, 10))
    recovered = scheduler.tick(NOW + timedelta(seconds=60))
    assert recovered is not None and recovered.observations == 1
    assert connector.get_calls == 2
    assert scheduler.status(NOW + timedelta(seconds=60)).last_error is None
    assert repository.list_attempts() == []


@pytest.mark.parametrize(
    "moment,next_day",
    [
        (datetime(2026, 3, 29, 0, tzinfo=UTC), "2026-04-05"),
        (datetime(2026, 10, 25, 1, 12, tzinfo=UTC), "2026-11-01"),
    ],
)
def test_clock_changes_do_not_create_nonexistent_or_second_ambiguous_runs(
    repository: Repository,
    moment: datetime,
    next_day: str,
):
    repository.upsert_merchant(
        Merchant(
            "shop",
            "Créneau de nuit fictif",
            (ScheduleWindow(6, time(2, 10), time(2, 20)),),
        )
    )
    scheduler, connector, _ = make_scheduler(repository)
    scheduler.start(moment)
    assert scheduler.tick(moment) is None
    status = scheduler.status(moment)
    assert status.next_check is not None
    assert status.next_check.date().isoformat() == next_day
    assert connector.get_calls == 0
