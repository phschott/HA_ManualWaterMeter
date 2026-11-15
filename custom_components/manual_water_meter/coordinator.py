"""Shared runtime state for the Manual Water Meter integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_REMINDER_DAYS,
    DEFAULT_CURRENCY,
    DEFAULT_LANGUAGE,
    DEFAULT_PRICE,
    DEFAULT_REMINDER_DAYS,
    DOMAIN,
    EVENT_REMINDER,
    NOTIFICATION_TEXTS,
    SIGNAL_UPDATE,
    STORAGE_VERSION,
)
from .statistics_import import StatTarget, record_reading

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# How often we re-evaluate whether a reading is overdue.
CHECK_INTERVAL = timedelta(hours=1)


class ManualWaterMeterCoordinator:
    """Holds the meter reading, persists it, and drives the reminder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.reading: float | None = None
        self.last_updated: datetime | None = None
        self.price: float = DEFAULT_PRICE
        self.volume: float = 0.0
        self.cost: float = 0.0
        self._reminder_notified: bool = False
        self._unsub_timer: callback | None = None

    # --- Configuration helpers ------------------------------------------------

    @property
    def reminder_days(self) -> int:
        """Return the configured reminder interval in days."""
        return int(self.entry.options.get(CONF_REMINDER_DAYS, DEFAULT_REMINDER_DAYS))

    @property
    def signal(self) -> str:
        """Dispatcher signal entities listen on for state changes."""
        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Device all entities are grouped under."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Manual Water Meter",
            entry_type=None,
        )

    # --- Derived state --------------------------------------------------------

    @property
    def days_since_update(self) -> float | None:
        """Days elapsed since the last reading, or None if never set."""
        if self.last_updated is None:
            return None
        delta = dt_util.utcnow() - self.last_updated
        return round(delta.total_seconds() / 86400, 2)

    @property
    def reminder_due(self) -> bool:
        """Whether a new reading is overdue."""
        if self.last_updated is None:
            # No reading ever recorded: nudge the user to take the first one.
            return True
        days = self.days_since_update
        return days is not None and days >= self.reminder_days

    # --- Persistence ----------------------------------------------------------

    async def async_load(self) -> None:
        """Restore state from disk."""
        data = await self._store.async_load()
        if not data:
            return
        self.reading = data.get("reading")
        timestamp = data.get("last_updated")
        self.last_updated = dt_util.parse_datetime(timestamp) if timestamp else None
        self.price = data.get("price", DEFAULT_PRICE)
        self.volume = data.get("volume", 0.0)
        self.cost = data.get("cost", 0.0)
        self._reminder_notified = data.get("reminder_notified", False)

    async def _async_save(self) -> None:
        """Write state to disk."""
        await self._store.async_save(
            {
                "reading": self.reading,
                "last_updated": (
                    self.last_updated.isoformat() if self.last_updated else None
                ),
                "price": self.price,
                "volume": self.volume,
                "cost": self.cost,
                "reminder_notified": self._reminder_notified,
            }
        )

    # --- Statistics target ----------------------------------------------------

    @property
    def stat_target(self) -> StatTarget:
        """External-statistics ids, names and currency for this meter."""
        # A statistic_id must match ^[\\da-z_]+:[\\da-z_]+$ (lowercase only), but
        # the config entry_id is an ULID that contains uppercase letters, so it
        # must be lowercased here or HA rejects it with "Invalid statistic_id".
        entry_id = self.entry.entry_id.lower()
        currency = self.hass.config.currency or DEFAULT_CURRENCY
        return StatTarget(
            water_id=f"{DOMAIN}:{entry_id}_water",
            water_name=f"{self.entry.title} water consumption",
            cost_id=f"{DOMAIN}:{entry_id}_cost",
            cost_name=f"{self.entry.title} water cost",
            currency=currency,
        )

    # --- Mutations ------------------------------------------------------------

    async def async_set_reading(self, value: float) -> None:
        """
        Record a new reading, spreading its consumption since the last one.

        Consumption between the previous reading and now is written as smoothed
        hourly statistics, so the Energy dashboard shows an even daily curve
        instead of one spike on the day the value is entered.
        """
        now = dt_util.utcnow()
        if (
            self.reading is not None
            and self.last_updated is not None
            and self.last_updated < now
            and value >= self.reading
        ):
            readings = [(self.last_updated, self.reading), (now, value)]
        else:
            readings = [(now, value)]
        self.volume, self.cost = record_reading(
            self.hass,
            self.stat_target,
            readings=readings,
            price=self.price,
            volume_offset=self.volume,
            cost_offset=self.cost,
        )

        self.reading = value
        self.last_updated = now
        self._reminder_notified = False
        persistent_notification.async_dismiss(self.hass, self._notification_id)
        await self._async_save()
        self._notify()

    async def async_set_price(self, value: float) -> None:
        """Update the current water price (does not alter past cost)."""
        self.price = value
        await self._async_save()
        self._notify()

    async def async_apply_import(
        self,
        *,
        reading: float,
        volume: float,
        cost: float,
        price: float | None,
        when: datetime,
    ) -> None:
        """
        Align live state with the last values of an imported history.

        Sets the reading, cumulative volume and cost directly (no delta accrual)
        so the next live reading smoothly continues from the last imported point.
        ``when`` is the date of that last point, so a following reading spreads
        its consumption from there.
        """
        self.reading = reading
        self.volume = volume
        self.cost = cost
        if price is not None:
            self.price = price
        self.last_updated = when
        self._reminder_notified = False
        persistent_notification.async_dismiss(self.hass, self._notification_id)
        await self._async_save()
        self._notify()

    # --- Reminder loop --------------------------------------------------------

    async def async_start(self) -> None:
        """Begin periodic reminder checks."""
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_check, CHECK_INTERVAL
        )
        # Evaluate once shortly after setup so state is correct immediately.
        await self._async_check()

    async def _async_check(self, _now: datetime | None = None) -> None:
        """Evaluate the reminder and refresh dependent entities."""
        if self.reminder_due and not self._reminder_notified:
            self._reminder_notified = True
            await self._async_save()
            self._fire_reminder()
        self._notify()

    @property
    def _notification_id(self) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}_reminder"

    @callback
    def _texts(self) -> dict[str, str]:
        """Return the notification texts for Home Assistant's language."""
        language = (self.hass.config.language or DEFAULT_LANGUAGE).split("-")[0]
        return NOTIFICATION_TEXTS.get(language, NOTIFICATION_TEXTS[DEFAULT_LANGUAGE])

    @callback
    def _fire_reminder(self) -> None:
        """Notify the user and fire an event that automations can use."""
        days = self.days_since_update
        texts = self._texts()
        if days is None:
            message = texts["message_never"].format(name=self.entry.title)
        else:
            message = texts["message_overdue"].format(
                name=self.entry.title, days=f"{days:.0f}"
            )
        persistent_notification.async_create(
            self.hass,
            message,
            title=texts["title"].format(name=self.entry.title),
            notification_id=self._notification_id,
        )
        self.hass.bus.async_fire(
            EVENT_REMINDER,
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.title,
                "days_since_update": days,
                "reminder_days": self.reminder_days,
            },
        )

    @callback
    def _notify(self) -> None:
        """Tell listening entities to refresh."""
        async_dispatcher_send(self.hass, self.signal)

    async def async_unload(self) -> None:
        """Stop the reminder loop."""
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
