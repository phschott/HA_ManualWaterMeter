"""The Manual Water Meter integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .const import PLATFORMS
from .coordinator import ManualWaterMeterCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

type ManualWaterMeterConfigEntry = ConfigEntry[ManualWaterMeterCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: ManualWaterMeterConfigEntry
) -> bool:
    """Set up Manual Water Meter from a config entry."""
    coordinator = ManualWaterMeterCoordinator(hass, entry)
    await coordinator.async_load()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ManualWaterMeterConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ManualWaterMeterConfigEntry
) -> bool:
    """Unload a config entry."""
    coordinator = entry.runtime_data
    await coordinator.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
