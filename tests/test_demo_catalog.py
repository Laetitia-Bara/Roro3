"""Le catalogue fictif suit les réglages sans changer l'identité des paniers."""

from dataclasses import replace
from datetime import timedelta

from roro3.demo import DEMO_NOW, build_demo
from roro3.merchants import MerchantService
from roro3.models import RunPolicy


def by_merchant(application):
    return {offer.merchant_id: offer for offer in application.connector.get_offers()}


def test_new_merchant_is_observed_without_restarting(tmp_path):
    app = build_demo(tmp_path / "catalog.sqlite3")
    before = by_merchant(app)
    created = MerchantService(app.repo).create("Commerce fictif ajouté")
    after = by_merchant(app)
    assert after.keys() == before.keys() | {created.id}
    assert all(after[identifier] == offer for identifier, offer in before.items())
    cycle = app.monitor.run_once(DEMO_NOW)
    assert cycle.observations == 4
    assert any(row["merchant_id"] == created.id for row in app.repo.list_observations())
    assert app.connector.reserve_calls == []


def test_renaming_and_reordering_do_not_change_offer_identity(tmp_path):
    app = build_demo(tmp_path / "catalog.sqlite3")
    before = by_merchant(app)
    service = MerchantService(app.repo)
    merchant = service.get("demo-bakery")
    service.update(merchant.id, "AAA nouveau nom fictif", ())
    assert by_merchant(app) == before
    assert service.get(merchant.id).windows == tuple(
        window for window in merchant.windows if window.source == "estimated"
    )


def test_same_day_restart_keeps_offers_and_blocks_duplicates(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    app = build_demo(path)
    app.repo.set_policy(RunPolicy(reserve=True, dry_run=False))
    first = app.monitor.run_once(DEMO_NOW)
    before = by_merchant(app)
    restarted = build_demo(path, now=DEMO_NOW + timedelta(minutes=30))
    second = restarted.monitor.run_once(DEMO_NOW + timedelta(minutes=30))
    assert by_merchant(restarted) == before
    assert sum(result.outcome == "confirmed" for result in first.reservations) == 2
    assert sum(result.outcome == "confirmed" for result in second.reservations) == 0
    assert restarted.connector.reserve_calls == []
    assert len(restarted.repo.list_attempts()) == 2


def test_previous_demo_pickup_is_reused_after_upgrade(tmp_path):
    app = build_demo(tmp_path / "catalog.sqlite3")
    original = by_merchant(app)["demo-bakery"]
    legacy = replace(
        original,
        pickup_start=DEMO_NOW + timedelta(hours=1),
        pickup_end=DEMO_NOW + timedelta(hours=2),
    )
    app.repo.record_observation(legacy, DEMO_NOW)
    assert by_merchant(app)["demo-bakery"].pickup_start == legacy.pickup_start
    assert by_merchant(app)["demo-bakery"].id == "demo-offer-1"


def test_new_day_is_a_distinct_pickup_but_same_offer_identifier(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    first = build_demo(path)
    following = build_demo(path, now=DEMO_NOW + timedelta(days=1))
    before, after = by_merchant(first), by_merchant(following)
    for identifier, offer in before.items():
        assert after[identifier].id == offer.id
        assert after[identifier].pickup_start - offer.pickup_start == timedelta(days=1)


def test_injected_clock_advances_the_ui_scenario_without_restarting(tmp_path):
    current = [DEMO_NOW]
    app = build_demo(tmp_path / "clock.sqlite3", clock=lambda: current[0])
    before = by_merchant(app)
    current[0] += timedelta(days=1)
    after = by_merchant(app)
    assert before.keys() == after.keys()
    for identifier, offer in before.items():
        assert after[identifier].id == offer.id
        assert after[identifier].pickup_start > offer.pickup_start


def test_disabled_merchants_are_not_reseeded_and_no_cycle_runs_during_crud(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    app = build_demo(path)
    service = MerchantService(app.repo)
    before = app.repo.list_observations()
    for merchant in app.repo.list_merchants():
        service.set_active(merchant.id, False)
        service.set_watched(merchant.id, False)
    reopened = build_demo(path)
    assert all(
        not merchant.active and not merchant.watched for merchant in reopened.repo.list_merchants()
    )
    assert reopened.monitor.run_once(DEMO_NOW).observations == 0
    assert reopened.repo.list_observations() == before
    assert reopened.repo.list_attempts() == []
