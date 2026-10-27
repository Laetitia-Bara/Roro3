"""Validation des valeurs réellement reçues par le formulaire, sans navigateur."""

from datetime import time

import pytest

from roro3.merchant_ui import parse_manual_windows
from roro3.models import ScheduleWindow


def test_multiple_days_and_empty_schedule_are_accepted():
    assert parse_manual_windows([]) == ()
    assert parse_manual_windows([(1, "18:00", "18:15"), (3, "12:10", "12:30")]) == (
        ScheduleWindow(1, time(18), time(18, 15)),
        ScheduleWindow(3, time(12, 10), time(12, 30)),
    )


@pytest.mark.parametrize(
    "row",
    [
        (None, "18:00", "18:15"),
        (7, "18:00", "18:15"),
        (True, "18:00", "18:15"),
        (1, "", "18:15"),
        (1, "18:00", "18:00"),
        (1, "18:30", "18:00"),
        (1, "23:00", "01:00"),
        (1, "24:00", "24:15"),
        (1, "18:60", "19:15"),
        (1, "18:00:30", "18:15"),
    ],
)
def test_invalid_fields_raise_a_readable_validation_error(row):
    with pytest.raises(ValueError):
        parse_manual_windows([row])
