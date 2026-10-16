"""Shared runtime state for the Manual Water Meter integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_REMINDER_DAYS,
    DEFAULT_REMINDER_DAYS,
    DOMAIN,
    EVENT_REMINDER,
    SIGNAL_UPDATE,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# How often we re-evaluate whether a reading is overdue.
CHECK_INTERVAL = timedelta(hours=1)


class ManualWaterMeterCoordinator:
    """Holds the meter reading, persists it, and drives the reminder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.reading: float | None = None
        self.last_updated: datetime | None = None
        self._reminder_notified: bool = False
        self._unsub_timer: callback | None = None

    # --- Configuration helpers ------------------------------------------------

    @property
    def reminder_days(self) -> int:
        """Return the configured reminder interval in days."""
        return int(
            self.entry.options.get(CONF_REMINDER_DAYS, DEFAULT_REMINDER_DAYS)
        )

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
        self.last_updated = (
            dt_util.parse_datetime(timestamp) if timestamp else None
        )
        self._reminder_notified = data.get("reminder_notified", False)

    async def _async_save(self) -> None:
        """Write state to disk."""
        await self._store.async_save(
            {
                "reading": self.reading,
                "last_updated": (
                    self.last_updated.isoformat() if self.last_updated else None
                ),
                "reminder_notified": self._reminder_notified,
            }
        )

    # --- Mutations ------------------------------------------------------------

    async def async_set_reading(self, value: float) -> None:
        """Record a new meter reading and reset the reminder."""
        self.reading = value
        self.last_updated = dt_util.utcnow()
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
    def _fire_reminder(self) -> None:
        """Notify the user and fire an event that automations can use."""
        days = self.days_since_update
        if days is None:
            message = (
                f"No reading has ever been recorded for '{self.entry.title}'. "
                "Please enter your current water meter value."
            )
        else:
            message = (
                f"It has been {days:.0f} day(s) since the last reading of "
                f"'{self.entry.title}'. Please update your water meter value."
            )
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"Water meter reading due — {self.entry.title}",
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
