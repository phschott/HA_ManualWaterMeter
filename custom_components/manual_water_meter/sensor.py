"""Sensor platform: Energy-dashboard water source + reminder helper."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ManualWaterMeterConfigEntry
from .coordinator import ManualWaterMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ManualWaterMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            WaterConsumptionSensor(coordinator),
            DaysSinceReadingSensor(coordinator),
        ]
    )


class _BaseSensor(SensorEntity):
    """Common wiring for Manual Water Meter sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class WaterConsumptionSensor(_BaseSensor):
    """Exposes the meter reading for the HA Energy dashboard."""

    _attr_translation_key = "water"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:water"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_water"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.reading


class DaysSinceReadingSensor(_BaseSensor):
    """Number of days since the last manual reading."""

    _attr_translation_key = "days_since_reading"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_days_since_reading"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.days_since_update
