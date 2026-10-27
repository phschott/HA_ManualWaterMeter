"""Number platform: the manual meter reading and the water price inputs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DEFAULT_CURRENCY,
    METER_MAX,
    METER_MIN,
    METER_STEP,
    PRICE_MAX,
    PRICE_MIN,
    PRICE_STEP,
)

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
    """Set up the meter reading and water price number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ManualWaterMeterNumber(coordinator),
            WaterPriceNumber(coordinator),
        ]
    )


class _BaseNumber(NumberEntity):
    """Common wiring for Manual Water Meter number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info

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


class ManualWaterMeterNumber(_BaseNumber):
    """Editable entry for the current water meter reading (m³)."""

    _attr_translation_key = "meter_reading"
    _attr_native_min_value = METER_MIN
    _attr_native_max_value = METER_MAX
    _attr_native_step = METER_STEP
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the meter reading entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_meter_reading"

    @property
    def native_value(self) -> float | None:
        """Return the current meter reading."""
        return self._coordinator.reading

    async def async_set_native_value(self, value: float) -> None:
        """Record a new meter reading."""
        await self._coordinator.async_set_reading(value)
        self.async_write_ha_state()


class WaterPriceNumber(_BaseNumber):
    """Editable entry for the current water price (currency per m³)."""

    _attr_translation_key = "water_price"
    _attr_native_min_value = PRICE_MIN
    _attr_native_max_value = PRICE_MAX
    _attr_native_step = PRICE_STEP
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the water price entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_water_price"
        currency = coordinator.hass.config.currency or DEFAULT_CURRENCY
        self._attr_native_unit_of_measurement = f"{currency}/m³"

    @property
    def native_value(self) -> float | None:
        """Return the current water price."""
        return self._coordinator.price

    async def async_set_native_value(self, value: float) -> None:
        """Update the current water price."""
        await self._coordinator.async_set_price(value)
        self.async_write_ha_state()
