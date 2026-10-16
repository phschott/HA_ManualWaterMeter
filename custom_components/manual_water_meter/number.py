"""Number platform: the manual meter reading input."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ManualWaterMeterConfigEntry
from .const import METER_MAX, METER_MIN, METER_STEP
from .coordinator import ManualWaterMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ManualWaterMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the meter reading number entity."""
    async_add_entities([ManualWaterMeterNumber(entry.runtime_data)])


class ManualWaterMeterNumber(NumberEntity):
    """Editable entry for the current water meter reading (m³)."""

    _attr_has_entity_name = True
    _attr_translation_key = "meter_reading"
    _attr_native_min_value = METER_MIN
    _attr_native_max_value = METER_MAX
    _attr_native_step = METER_STEP
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_meter_reading"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return the current meter reading."""
        return self._coordinator.reading

    async def async_set_native_value(self, value: float) -> None:
        """Record a new meter reading."""
        await self._coordinator.async_set_reading(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to state changes from other sources (e.g. services)."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
