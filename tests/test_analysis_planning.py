from datetime import UTC, datetime, time

import pytest

from roro3.analysis import estimate_windows
from roro3.demo import build_demo
from roro3.models import ScheduleWindow
from roro3.planning import next_window


def test_demo_estimates_three_distinct_tuesdays_in_paris(tmp_path):
    demo = build_demo(tmp_path / "demo.sqlite3")
    windows = estimate_windows(demo.repo.list_observations(), "demo-bakery")
    assert windows == (ScheduleWindow(1, time(18), time(18, 15), "estimated", 3),)


def test_repeated_scans_same_day_and_first_presence_do_not_create_estimate():
    rows = [
        {
            "merchant_id": "shop",
            "observed_at": f"2026-10-06T16:0{minute}:00+00:00",
            "event": "became_available",
        }
        for minute in range(1, 4)
    ]
    rows += [
        {
            "merchant_id": "shop",
            "observed_at": "2026-10-13T16:08:00+00:00",
            "event": "first_seen_available",
        },
        {
            "merchant_id": "shop",
            "observed_at": "2026-10-20T16:08:00+00:00",
            "event": "first_seen_available",
        },
    ]
    assert estimate_windows(rows, "shop") == ()


def test_next_window_uses_calendar_date_across_autumn_clock_change():
    window = ScheduleWindow(6, time(18), time(18, 15))
    result = next_window([window], datetime(2026, 10, 24, 18, tzinfo=UTC))
    assert result is not None
    assert result.hour == 18
    assert result.astimezone(UTC) == datetime(2026, 10, 25, 17, tzinfo=UTC)


def test_spring_nonexistent_time_is_skipped():
    window = ScheduleWindow(6, time(2, 15), time(2, 30))
    result = next_window([window], datetime(2026, 3, 29, 0, tzinfo=UTC))
    assert result is not None
    assert result.date().isoformat() == "2026-04-05"


def test_ambiguous_autumn_window_is_not_run_twice():
    window = ScheduleWindow(6, time(2, 10), time(2, 20))
    result = next_window([window], datetime(2026, 10, 25, 1, 12, tzinfo=UTC))
    assert result is not None
    assert result.date().isoformat() == "2026-11-01"


def test_active_window_and_empty_schedule():
    now = datetime(2026, 10, 27, 17, 7, tzinfo=UTC)
    assert next_window([ScheduleWindow(1, time(18), time(18, 15))], now) == now
    assert next_window([], now) is None


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        next_window([], datetime(2026, 10, 27))
