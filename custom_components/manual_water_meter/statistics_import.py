"""
Parse a water-history CSV and import it as long-term statistics.

The CSV holds absolute meter readings (``date,reading`` in m³) and an optional
``price`` column (currency per m³ in effect from that date). Consumption between
two readings is spread evenly across every hour of the interval, so the Energy
dashboard shows a smooth history; cost is derived hourly from consumption times
the price in effect (a step function). Statistics are written as **external
statistics** owned by the integration (``async_add_external_statistics``, upsert
by ``statistic_id`` + hour), so re-importing the same range is idempotent and the
Energy dashboard shows no ``state_class`` warning.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.const import UnitOfVolume
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MIN_CSV_COLUMNS, MIN_READINGS

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import tzinfo

    from homeassistant.core import HomeAssistant

Reading = tuple[datetime, float]
PricePoint = tuple[datetime, float]


class Record(NamedTuple):
    """One CSV row: a timestamp, a meter reading and an optional price."""

    when: datetime
    reading: float
    price: float | None


@dataclass(frozen=True)
class StatTarget:
    """External statistic ids, names and currency for one water meter."""

    water_id: str
    water_name: str
    cost_id: str
    cost_name: str
    currency: str


@dataclass(frozen=True)
class ImportSummary:
    """Outcome of an import, returned for user feedback."""

    consumption_points: int
    cost_points: int
    first_date: datetime
    last_date: datetime
    last_reading: float
    last_volume: float
    last_cost: float
    last_price: float | None


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


def parse_records(content: str, default_tz: tzinfo) -> list[Record]:
    """Parse CSV text into a sorted, validated list of records."""
    rows = [line for line in content.splitlines() if line.strip()]
    if not rows:
        message = "the CSV is empty"
        raise ValueError(message)

    delimiter = _detect_delimiter(rows[0])
    first_field = rows[0].split(delimiter)[0]
    start = 1 if _looks_like_header(first_field, default_tz) else 0

    records: list[Record] = []
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
        price: float | None = None
        if len(parts) > MIN_CSV_COLUMNS and parts[2].strip():
            try:
                price = _parse_number(parts[2])
            except ValueError as err:
                message = f"line {offset}: invalid price {parts[2]!r}"
                raise ValueError(message) from err
        records.append(Record(when, reading, price))

    records.sort(key=lambda item: item.when)

    if len(records) < MIN_READINGS:
        message = "at least two readings are required to import a history"
        raise ValueError(message)

    for previous, current in itertools.pairwise(records):
        if current.reading < previous.reading:
            message = (
                f"readings must not decrease (a meter only goes up): "
                f"{current.reading} after {previous.reading} "
                f"at {current.when.isoformat()}"
            )
            raise ValueError(message)

    return records


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


def _price_at(
    price_points: list[PricePoint], when: datetime, fallback: float | None
) -> float | None:
    """Return the price in effect at ``when`` (step function), else fallback."""
    effective: float | None = None
    for point_when, price in price_points:
        if point_when <= when:
            effective = price
        else:
            break
    if effective is not None:
        return effective
    if price_points:
        # ``when`` precedes the first priced row: use the earliest known price.
        return price_points[0][1]
    return fallback


def _build_cumulative(
    readings: list[Reading],
    offset: float,
    increment: Callable[[float, datetime], float],
) -> list[StatisticData]:
    """
    Build hourly cumulative statistics starting from ``offset``.

    ``sum`` is a running total (consumption or cost) that starts at ``offset`` on
    the first reading and grows by ``increment(consumed, hour)`` each hour. It is
    never the absolute meter value, so the Energy dashboard shows the per-period
    delta (smoothed over the interval) instead of a spike equal to the reading.
    """
    start = _floor_hour(readings[0][0])
    end = _floor_hour(readings[-1][0])
    total = offset
    stats: list[StatisticData] = [StatisticData(start=start, state=total, sum=total)]
    hour = start
    while hour < end:
        nxt = hour + timedelta(hours=1)
        consumed = _interpolate(readings, nxt) - _interpolate(readings, hour)
        total += increment(consumed, hour)
        stats.append(StatisticData(start=nxt, state=total, sum=total))
        hour = nxt
    return stats


def build_consumption_statistics(
    readings: list[Reading], volume_offset: float = 0.0
) -> list[StatisticData]:
    """Build hourly cumulative-consumption points (m³ consumed since start)."""
    return _build_cumulative(readings, volume_offset, lambda consumed, _hour: consumed)


def build_cost_statistics(
    readings: list[Reading],
    price_points: list[PricePoint],
    fallback_price: float | None,
    cost_offset: float = 0.0,
) -> list[StatisticData] | None:
    """Build hourly cumulative-cost points, or None when no price is available."""
    if not price_points and fallback_price is None:
        return None

    def increment(consumed: float, hour: datetime) -> float:
        price = _price_at(price_points, hour, fallback_price) or 0.0
        return consumed * price

    return _build_cumulative(readings, cost_offset, increment)


def _water_metadata(target: StatTarget) -> StatisticMetaData:
    """Return external-statistics metadata for the water consumption series."""
    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=target.water_name,
        source=DOMAIN,
        statistic_id=target.water_id,
        unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    )


def _cost_metadata(target: StatTarget) -> StatisticMetaData:
    """Return external-statistics metadata for the water cost series."""
    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=target.cost_name,
        source=DOMAIN,
        statistic_id=target.cost_id,
        unit_of_measurement=target.currency,
    )


async def async_import_history(
    hass: HomeAssistant,
    target: StatTarget,
    *,
    content: str,
    fallback_price: float | None = None,
) -> ImportSummary:
    """
    Parse ``content`` and import consumption (and cost) statistics.

    An import defines a fresh history: cumulative volume and cost both start at
    zero on the first CSV row.
    """
    default_tz = dt_util.DEFAULT_TIME_ZONE or dt_util.UTC
    records = parse_records(content, default_tz)
    readings: list[Reading] = [(r.when, r.reading) for r in records]
    price_points: list[PricePoint] = [
        (r.when, r.price) for r in records if r.price is not None
    ]

    consumption = build_consumption_statistics(readings)
    async_add_external_statistics(hass, _water_metadata(target), consumption)
    last_volume = float(consumption[-1]["sum"])

    cost = build_cost_statistics(readings, price_points, fallback_price)
    last_cost = 0.0
    cost_points = 0
    if cost is not None:
        async_add_external_statistics(hass, _cost_metadata(target), cost)
        last_cost = float(cost[-1]["sum"])
        cost_points = len(cost)

    last_price = _price_at(price_points, _floor_hour(records[-1].when), fallback_price)

    return ImportSummary(
        consumption_points=len(consumption),
        cost_points=cost_points,
        first_date=records[0].when,
        last_date=records[-1].when,
        last_reading=records[-1].reading,
        last_volume=last_volume,
        last_cost=last_cost,
        last_price=last_price,
    )


def record_reading(  # noqa: PLR0913 - keyword-only, all required
    hass: HomeAssistant,
    target: StatTarget,
    *,
    readings: list[Reading],
    price: float | None,
    volume_offset: float,
    cost_offset: float,
) -> tuple[float, float]:
    """
    Inject smoothed statistics for a live reading; return (volume, cost).

    ``readings`` is the previous and new ``(timestamp, reading)`` points (or a
    single point for the very first reading). Consumption is spread hourly across
    the interval; the cumulative volume and cost continue from their offsets.
    """
    consumption = build_consumption_statistics(readings, volume_offset)
    async_add_external_statistics(hass, _water_metadata(target), consumption)
    new_volume = float(consumption[-1]["sum"])

    new_cost = cost_offset
    if price is not None:
        cost = build_cost_statistics(readings, [], price, cost_offset=cost_offset)
        if cost is not None:
            async_add_external_statistics(hass, _cost_metadata(target), cost)
            new_cost = float(cost[-1]["sum"])
    return new_volume, new_cost
