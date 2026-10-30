"""Historique : vrais instants, dates locales et analyse avant pagination."""

from datetime import UTC, date, datetime, timedelta

import pytest

from roro3.demo import build_demo
from roro3.history import HistoryFilters, HistoryService
from roro3.history_ui import parse_filters
from roro3.models import Merchant, Offer
from roro3.storage import Repository


def test_summary_and_patterns_cover_all_pages_and_query_is_read_only(tmp_path):
    repo = build_demo(tmp_path / "demo.sqlite3").repo
    with repo.connection() as db:
        before = "\n".join(db.iterdump())
    result = HistoryService(repo).query(HistoryFilters("demo-bakery"), page_size=1, page=99)
    assert result.total == result.summary.observation_count == 6
    assert result.total_pages == result.page == 6
    assert len(result.rows) == 1
    assert result.summary.observed_days == result.summary.transition_count == 3
    assert result.patterns[0].eligible and result.patterns[0].distinct_days == 3
    with repo.connection() as db:
        assert "\n".join(db.iterdump()) == before


def test_history_sorts_real_time_after_backfill_and_keeps_disabled_merchants(tmp_path):
    repo = Repository(tmp_path / "history.sqlite3")
    repo.upsert_merchant(Merchant("shop", "Commerce", active=False))
    now = datetime(2026, 10, 30, 17, tzinfo=UTC)
    for day in (0, -2, -1):
        instant = now + timedelta(days=day)
        repo.record_observation(Offer(str(day), "shop", now, now + timedelta(hours=1), 1), instant)
    result = HistoryService(repo).query(HistoryFilters("shop"))
    assert [row["offer_id"] for row in result.rows] == ["0", "-1", "-2"]
    assert result.patterns == ()  # Premières présences seules.


@pytest.mark.parametrize(
    "day,start,end",
    [
        (date(2026, 3, 29), "2026-03-28T23:00:00+00:00", "2026-03-29T21:59:59+00:00"),
        (date(2026, 10, 25), "2026-10-24T22:00:00+00:00", "2026-10-25T22:59:59+00:00"),
    ],
)
def test_inclusive_local_dates_across_clock_changes(tmp_path, day, start, end):
    repo = Repository(tmp_path / "history.sqlite3")
    low, high = datetime.fromisoformat(start), datetime.fromisoformat(end)
    for i, instant in enumerate(
        (low - timedelta(seconds=1), low, high, high + timedelta(seconds=1))
    ):
        repo.record_observation(Offer(str(i), "old-shop", low, high, 0), instant)
    result = HistoryService(repo).query(HistoryFilters(start_date=day, end_date=day))
    assert [row["offer_id"] for row in result.rows] == ["2", "1"]
    assert result.summary.observed_days == 1


def test_multiple_transitions_same_day_do_not_reach_estimation_threshold(tmp_path):
    repo = Repository(tmp_path / "history.sqlite3", dataset_kind="family")
    repo.upsert_merchant(Merchant("shop", "Commerce"))
    start = datetime(2026, 10, 30, 17, tzinfo=UTC)
    for i, amount in enumerate((0, 2, 0, 1, 0, 1)):
        repo.record_manual_observation("shop", amount, start + timedelta(minutes=i), "Europe/Paris")
    result = HistoryService(repo).query(HistoryFilters("shop", "became_available"), page_size=1)
    assert result.total == 3
    assert result.patterns[0].distinct_days == 1
    assert not result.patterns[0].eligible


@pytest.mark.parametrize(
    "args", [{"page": True}, {"page": 0}, {"page_size": 101}, {"page_size": 0}]
)
def test_invalid_pagination_is_rejected(tmp_path, args):
    with pytest.raises(ValueError):
        HistoryService(Repository(tmp_path / "empty.sqlite3")).query(**args)


def test_empty_and_invalid_filter_form(tmp_path):
    assert HistoryService(Repository(tmp_path / "empty.sqlite3")).query().total == 0
    assert parse_filters("", "", "", "") == HistoryFilters()
    with pytest.raises(ValueError):
        parse_filters("", "", "2026-11-02", "2026-10-30")
