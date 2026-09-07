"""
Cron expression parsing, validation and next-run calculation.

Supports the standard 5-field crontab syntax:

    minute hour day-of-month month day-of-week
    0-59   0-23 1-31         1-12  0-6 (0 = Sunday, 7 also accepted)

Each field accepts ``*``, ``a``, ``a-b``, ``*/n``, ``a-b/n`` and comma
separated lists of those. Three-letter month (JAN..DEC) and weekday
(SUN..SAT) names are accepted. The convenience aliases ``@hourly``,
``@daily``/``@midnight``, ``@weekly``, ``@monthly`` and ``@yearly``/``@annually``
are also supported.

Implemented in-tree rather than pulling in a scheduling dependency so that
validation errors and next-run times stay consistent between the API layer
and the scheduler loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

try:  # Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9 is unsupported anyway
    ZoneInfo = None  # type: ignore

    class ZoneInfoNotFoundError(Exception):  # type: ignore
        pass


class CronError(ValueError):
    """Raised when a cron expression cannot be parsed."""


MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DAY_NAMES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}

ALIASES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

# (name, min, max, name_map)
FIELDS = (
    ("minute", 0, 59, None),
    ("hour", 0, 23, None),
    ("day of month", 1, 31, None),
    ("month", 1, 12, MONTH_NAMES),
    ("day of week", 0, 6, DAY_NAMES),
)

# A cron expression can legitimately have no match for years (e.g. "0 0 30 2 *"),
# so the search is bounded rather than looping forever.
MAX_LOOKAHEAD_DAYS = 366 * 5


def _parse_value(token: str, field_name: str, low: int, high: int, names) -> int:
    token = token.strip().lower()
    if names and token in names:
        value = names[token]
    else:
        try:
            value = int(token)
        except ValueError:
            raise CronError(f"Invalid {field_name} value: '{token}'")
    # Cron allows 7 as Sunday in the day-of-week field.
    if field_name == "day of week" and value == 7:
        value = 0
    if value < low or value > high:
        raise CronError(
            f"{field_name.capitalize()} value {value} is out of range ({low}-{high})"
        )
    return value


def _parse_field(expr: str, field_name: str, low: int, high: int, names) -> Set[int]:
    values: Set[int] = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"Empty {field_name} entry in '{expr}'")

        step = 1
        if "/" in part:
            base, _, step_str = part.partition("/")
            try:
                step = int(step_str)
            except ValueError:
                raise CronError(f"Invalid step '{step_str}' in {field_name}")
            if step < 1:
                raise CronError(f"Step must be >= 1 in {field_name}")
            part = base.strip() or "*"

        if part == "*":
            start, end = low, high
        elif "-" in part[1:]:  # part[1:] so a leading '-' is still an error
            start_str, _, end_str = part.partition("-")
            start = _parse_value(start_str, field_name, low, high, names)
            end = _parse_value(end_str, field_name, low, high, names)
            if start > end:
                raise CronError(
                    f"Invalid {field_name} range '{part}': start is after end"
                )
        else:
            start = _parse_value(part, field_name, low, high, names)
            end = start if step == 1 else high

        values.update(range(start, end + 1, step))

    if not values:
        raise CronError(f"No values matched for {field_name} in '{expr}'")
    return values


class CronSchedule:
    """A parsed 5-field cron expression."""

    __slots__ = ("expression", "minutes", "hours", "days", "months", "weekdays",
                 "_dom_restricted", "_dow_restricted")

    def __init__(self, expression: str):
        raw = (expression or "").strip()
        if not raw:
            raise CronError("Cron expression is empty")

        normalized = ALIASES.get(raw.lower(), raw)
        parts = normalized.split()
        if len(parts) != 5:
            raise CronError(
                "Cron expression must have exactly 5 fields "
                "(minute hour day-of-month month day-of-week), "
                f"got {len(parts)}"
            )

        self.expression = raw
        parsed = [
            _parse_field(parts[i], name, low, high, names)
            for i, (name, low, high, names) in enumerate(FIELDS)
        ]
        self.minutes, self.hours, self.days, self.months, self.weekdays = parsed

        # Standard cron semantics: when both day-of-month and day-of-week are
        # restricted the job runs when EITHER matches; otherwise both must match.
        self._dom_restricted = parts[2].strip() != "*"
        self._dow_restricted = parts[4].strip() != "*"

    def matches(self, moment: datetime) -> bool:
        """True if `moment` (naive local-to-its-timezone) satisfies the schedule."""
        if moment.minute not in self.minutes:
            return False
        if moment.hour not in self.hours:
            return False
        if moment.month not in self.months:
            return False

        # Python: Monday == 0; cron: Sunday == 0
        cron_weekday = (moment.weekday() + 1) % 7
        dom_match = moment.day in self.days
        dow_match = cron_weekday in self.weekdays

        if self._dom_restricted and self._dow_restricted:
            return dom_match or dow_match
        return dom_match and dow_match

    def next_run(self, after: datetime) -> Optional[datetime]:
        """
        Return the first matching minute strictly after `after`.

        `after` must be timezone-aware; the result carries the same tzinfo.
        Returns None when nothing matches within the lookahead window.
        """
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = after + timedelta(days=MAX_LOOKAHEAD_DAYS)

        while candidate <= limit:
            if candidate.month not in self.months:
                # Jump to the first minute of the next month.
                if candidate.month == 12:
                    candidate = candidate.replace(
                        year=candidate.year + 1, month=1, day=1, hour=0, minute=0
                    )
                else:
                    candidate = candidate.replace(
                        month=candidate.month + 1, day=1, hour=0, minute=0
                    )
                continue

            if not self._day_matches(candidate):
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue

            if candidate.hour not in self.hours:
                candidate += timedelta(hours=1)
                candidate = candidate.replace(minute=0)
                continue

            if candidate.minute not in self.minutes:
                candidate += timedelta(minutes=1)
                continue

            return candidate

        return None

    def _day_matches(self, moment: datetime) -> bool:
        cron_weekday = (moment.weekday() + 1) % 7
        dom_match = moment.day in self.days
        dow_match = cron_weekday in self.weekdays
        if self._dom_restricted and self._dow_restricted:
            return dom_match or dow_match
        return dom_match and dow_match


def validate_cron(expression: str) -> CronSchedule:
    """Parse an expression, raising CronError with a readable message."""
    return CronSchedule(expression)


def validate_timezone(name: Optional[str]) -> str:
    """Return a valid IANA timezone name, raising CronError otherwise."""
    tz_name = (name or "UTC").strip() or "UTC"
    if tz_name.upper() == "UTC":
        return "UTC"
    if ZoneInfo is None:  # pragma: no cover
        raise CronError("Timezone support is unavailable on this Python build")
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise CronError(f"Unknown timezone: '{tz_name}'")
    return tz_name


def _tzinfo(tz_name: Optional[str]):
    tz_name = (tz_name or "UTC").strip() or "UTC"
    if tz_name.upper() == "UTC" or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return timezone.utc


def next_run_utc(
    expression: str,
    tz_name: str = "UTC",
    after: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Compute the next run time for `expression` in `tz_name`, returned in UTC.

    Raises CronError if the expression is invalid.
    """
    schedule = validate_cron(expression)
    tz = _tzinfo(tz_name)
    reference = after or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    local_next = schedule.next_run(reference.astimezone(tz))
    if local_next is None:
        return None
    return local_next.astimezone(timezone.utc)


def describe(expression: str) -> str:
    """Human-readable summary used in API responses and the UI."""
    try:
        schedule = validate_cron(expression)
    except CronError as exc:
        return str(exc)

    def summarize(values: Set[int], low: int, high: int, label: str) -> str:
        if len(values) == high - low + 1:
            return f"every {label}"
        ordered = sorted(values)
        if len(ordered) > 6:
            return f"{len(ordered)} selected {label}s"
        return f"{label} {', '.join(str(v) for v in ordered)}"

    return "; ".join([
        summarize(schedule.minutes, 0, 59, "minute"),
        summarize(schedule.hours, 0, 23, "hour"),
        summarize(schedule.days, 1, 31, "day"),
        summarize(schedule.months, 1, 12, "month"),
        summarize(schedule.weekdays, 0, 6, "weekday"),
    ])
