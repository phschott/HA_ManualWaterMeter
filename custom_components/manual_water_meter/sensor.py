"""Sensor platform: Energy-dashboard water source + reminder helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime, UnitOfVolume
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DEFAULT_CURRENCY, DOMAIN, SERVICE_IMPORT_HISTORY
from .services import IMPORT_HISTORY_SCHEMA, read_csv_file
from .statistics_import import async_import_history as import_water_history

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
    """Set up the sensor entities and the import_history entity service."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            WaterConsumptionSensor(coordinator),
            WaterCostSensor(coordinator),
            DaysSinceReadingSensor(coordinator),
        ]
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_IMPORT_HISTORY,
        IMPORT_HISTORY_SCHEMA,
        "async_import_history",
    )


class _BaseSensor(SensorEntity):
    """Common wiring for Manual Water Meter sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._attr_device_info = coordinator.device_info

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


class WaterConsumptionSensor(_BaseSensor):
    """Exposes the meter reading for the HA Energy dashboard."""

    _attr_translation_key = "water"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:water"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the water consumption sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_water"

    @property
    def native_value(self) -> float | None:
        """Return the current meter reading."""
        return self._coordinator.reading

    async def async_import_history(
        self,
        filename: str | None = None,
        csv: str | None = None,
        price: float | None = None,
        *,
        update_current: bool = True,
    ) -> None:
        """Import a consumption (and cost) history (import_history handler)."""
        if not filename and not csv:
            message = "provide either 'filename' or 'csv'"
            raise ServiceValidationError(message)

        if filename:
            content = await self.hass.async_add_executor_job(
                read_csv_file, self.hass, filename
            )
        else:
            content = csv or ""

        entry_id = self._coordinator.entry.entry_id
        cost_statistic_id = er.async_get(self.hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry_id}_cost"
        )
        currency = self.hass.config.currency or DEFAULT_CURRENCY

        try:
            summary = await import_water_history(
                self.hass,
                statistic_id=self.entity_id,
                cost_statistic_id=cost_statistic_id,
                content=content,
                currency=currency,
                fallback_price=price,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

        if update_current:
            await self._coordinator.async_apply_import(
                reading=summary.last_reading,
                cost=summary.last_cost,
                price=summary.last_price,
            )


class WaterCostSensor(_BaseSensor):
    """Cumulative water cost, for the Energy dashboard's total-cost option."""

    _attr_translation_key = "water_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the water cost sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cost"
        self._attr_native_unit_of_measurement = (
            coordinator.hass.config.currency or DEFAULT_CURRENCY
        )

    @property
    def native_value(self) -> float:
        """Return the cumulative water cost."""
        return self._coordinator.cost


class DaysSinceReadingSensor(_BaseSensor):
    """Number of days since the last manual reading."""

    _attr_translation_key = "days_since_reading"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ManualWaterMeterCoordinator) -> None:
        """Initialize the days-since-reading sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_days_since_reading"

    @property
    def native_value(self) -> float | None:
        """Return the number of days since the last reading."""
        return self._coordinator.days_since_update
