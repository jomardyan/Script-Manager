"""
Tests for the cron expression parser used by the scheduler.
"""
from datetime import datetime, timezone

import pytest

from app.services.cron import (
    CronError, describe, next_run_utc, validate_cron, validate_timezone,
)

# A Sunday, so day-of-week edge cases are exercised.
BASE = datetime(2026, 9, 6, 13, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("0 * * * *", datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc)),
        ("*/15 * * * *", datetime(2026, 9, 6, 13, 45, tzinfo=timezone.utc)),
        ("30 2 * * 1-5", datetime(2026, 9, 7, 2, 30, tzinfo=timezone.utc)),
        ("@daily", datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)),
        ("0 9 * * MON", datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)),
        # 2027 is not a leap year, so the next 29 February is in 2028.
        ("0 0 29 2 *", datetime(2028, 2, 29, 0, 0, tzinfo=timezone.utc)),
    ],
)
def test_next_run_utc(expression, expected):
    assert next_run_utc(expression, "UTC", BASE) == expected


def test_next_run_respects_timezone():
    """Noon in New York is 16:00 UTC during daylight saving time."""
    assert next_run_utc("0 12 * * *", "America/New_York", BASE) == datetime(
        2026, 9, 6, 16, 0, tzinfo=timezone.utc
    )


def test_day_of_month_or_day_of_week_semantics():
    """When both day fields are restricted, cron fires when either matches."""
    schedule = validate_cron("0 0 1 * MON")
    # 1 September 2026 is a Tuesday: matches on day-of-month alone.
    assert schedule.matches(datetime(2026, 9, 1, 0, 0))
    # 7 September 2026 is a Monday: matches on day-of-week alone.
    assert schedule.matches(datetime(2026, 9, 7, 0, 0))
    assert not schedule.matches(datetime(2026, 9, 8, 0, 0))


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "* * *",
        "* * * * * *",
        "60 * * * *",
        "* 24 * * *",
        "* * * * 9",
        "* * 0 * *",
        "abc * * * *",
        "*/0 * * * *",
        "5-1 * * * *",
        "* * * 13 *",
    ],
)
def test_invalid_expressions_are_rejected(expression):
    with pytest.raises(CronError):
        validate_cron(expression)


def test_validate_timezone():
    assert validate_timezone(None) == "UTC"
    assert validate_timezone("utc") == "UTC"
    assert validate_timezone("Europe/Warsaw") == "Europe/Warsaw"
    with pytest.raises(CronError):
        validate_timezone("Mars/Olympus_Mons")


def test_describe_is_human_readable():
    assert "weekday" in describe("*/15 9-17 * * 1-5")
