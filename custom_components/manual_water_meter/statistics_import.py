"""
Parse a water-history CSV and import it as long-term statistics.

The CSV holds absolute meter readings (``date,reading`` in m³). Consumption
between two readings is spread evenly across every hour of the interval, so the
Energy dashboard shows a smooth history. Statistics are written through the
recorder's ``async_import_statistics`` (upsert by ``statistic_id`` + hour), which
makes re-importing the same range idempotent.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.util import dt as dt_util

from .const import MIN_CSV_COLUMNS, MIN_READINGS, RECORDER_SOURCE

if TYPE_CHECKING:
    from datetime import tzinfo

    from homeassistant.core import HomeAssistant

Reading = tuple[datetime, float]


@dataclass(frozen=True)
class ImportSummary:
    """Outcome of an import, returned for user feedback."""

    points: int
    first: Reading
    last: Reading

    @property
    def last_reading(self) -> float:
        """Return the most recent meter value found in the CSV."""
        return self.last[1]


def _detect_delimiter(header: str) -> str:
    """Pick ``;`` (common in French Excel) or default to ``,``."""
    if ";" in header and header.count(";") >= header.count(","):
        return ";"
    return ","


def _parse_number(raw: str) -> float:
    """Parse a float, tolerating a comma decimal separator."""
    return float(raw.strip().replace(",", "."))


def _parse_datetime(raw: str, default_tz: tzinfo) -> datetime:
    """Parse an ISO date or datetime into an aware UTC datetime."""
    text = raw.strip()
    parsed = dt_util.parse_datetime(text)
    if parsed is None:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError as err:
            message = f"invalid date/time: {raw!r}"
            raise ValueError(message) from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return dt_util.as_utc(parsed)


def _looks_like_header(first_field: str, default_tz: tzinfo) -> bool:
    """Return True when the first row is a header rather than data."""
    try:
        _parse_datetime(first_field, default_tz)
    except ValueError:
        return True
    return False


def parse_readings(content: str, default_tz: tzinfo) -> list[Reading]:
    """Parse CSV text into a sorted, validated list of meter readings."""
    rows = [line for line in content.splitlines() if line.strip()]
    if not rows:
        message = "the CSV is empty"
        raise ValueError(message)

    delimiter = _detect_delimiter(rows[0])
    first_field = rows[0].split(delimiter)[0]
    start = 1 if _looks_like_header(first_field, default_tz) else 0

    readings: list[Reading] = []
    for offset, raw in enumerate(rows[start:], start=start + 1):
        parts = raw.split(delimiter)
        if len(parts) < MIN_CSV_COLUMNS:
            message = f"line {offset}: expected at least 2 columns"
            raise ValueError(message)
        when = _parse_datetime(parts[0], default_tz)
        try:
            reading = _parse_number(parts[1])
        except ValueError as err:
            message = f"line {offset}: invalid reading {parts[1]!r}"
            raise ValueError(message) from err
        readings.append((when, reading))

    readings.sort(key=lambda item: item[0])

    if len(readings) < MIN_READINGS:
        message = "at least two readings are required to import a history"
        raise ValueError(message)

    for (_, previous), (when, current) in itertools.pairwise(readings):
        if current < previous:
            message = (
                f"readings must not decrease (a meter only goes up): "
                f"{current} after {previous} at {when.isoformat()}"
            )
            raise ValueError(message)

    return readings


def _floor_hour(value: datetime) -> datetime:
    """Return the datetime truncated to the start of its hour."""
    return value.replace(minute=0, second=0, microsecond=0)


def _interpolate(readings: list[Reading], when: datetime) -> float:
    """Linearly interpolate the meter value at ``when`` (clamped at the ends)."""
    if when <= readings[0][0]:
        return readings[0][1]
    if when >= readings[-1][0]:
        return readings[-1][1]
    for (t0, r0), (t1, r1) in itertools.pairwise(readings):
        if t0 <= when <= t1:
            span = (t1 - t0).total_seconds()
            if span == 0:
                return r1
            ratio = (when - t0).total_seconds() / span
            return r0 + (r1 - r0) * ratio
    return readings[-1][1]


def build_hourly_statistics(readings: list[Reading]) -> list[StatisticData]:
    """Build one hourly statistics point from the first to the last reading."""
    baseline = readings[0][1]
    current = _floor_hour(readings[0][0])
    end = _floor_hour(readings[-1][0])
    stats: list[StatisticData] = []
    while current <= end:
        value = _interpolate(readings, current)
        stats.append(StatisticData(start=current, state=value, sum=value - baseline))
        current += timedelta(hours=1)
    return stats


async def async_import_history(
    hass: HomeAssistant, *, statistic_id: str, content: str
) -> ImportSummary:
    """Parse ``content`` and import it as statistics for ``statistic_id``."""
    default_tz = dt_util.DEFAULT_TIME_ZONE or dt_util.UTC
    readings = parse_readings(content, default_tz)
    statistics = build_hourly_statistics(readings)

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=None,
        source=RECORDER_SOURCE,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    )
    async_import_statistics(hass, metadata, statistics)

    return ImportSummary(points=len(statistics), first=readings[0], last=readings[-1])
