"""Binary sensor platform: whether a new reading is due."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import ManualWaterMeterConfigEntry
    from .coordinator import ManualWaterMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ManualWaterMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the reminder binary sensor."""
    async_add_entities([ReminderBinarySensor(entry.runtime_data)])


class ReminderBinarySensor(BinarySensorEntity):
    """On when a new meter reading is overdue."""

    _attr_has_entity_name = True
    _attr_translation_key = "reminder"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:bell-alert"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the binary sensor."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reminder"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return True when a reading is due."""
        return self._coordinator.reminder_due

    @property
    def extra_state_attributes(self) -> dict[str, float | int | None]:
        """Expose the reminder context."""
        return {
            "reminder_days": self._coordinator.reminder_days,
            "days_since_update": self._coordinator.days_since_update,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
