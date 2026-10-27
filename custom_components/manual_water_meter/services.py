"""Helpers for the Manual Water Meter import_history entity service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CSV,
    ATTR_FILENAME,
    ATTR_PRICE,
    ATTR_UPDATE_CURRENT,
    PRICE_MAX,
    PRICE_MIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Extra fields for the entity service (entity targeting is added by HA).
IMPORT_HISTORY_SCHEMA = {
    vol.Exclusive(ATTR_FILENAME, "source"): cv.string,
    vol.Exclusive(ATTR_CSV, "source"): cv.string,
    vol.Optional(ATTR_PRICE): vol.All(
        vol.Coerce(float), vol.Range(min=PRICE_MIN, max=PRICE_MAX)
    ),
    vol.Optional(ATTR_UPDATE_CURRENT, default=True): cv.boolean,
}


def read_csv_file(hass: HomeAssistant, filename: str) -> str:
    """Read a CSV file, resolving relative paths under the config directory."""
    path = Path(filename)
    if path.is_absolute():
        if not hass.config.is_allowed_path(str(path)):
            message = f"access to {filename} is not allowed"
            raise ValueError(message)
    else:
        path = Path(hass.config.path(filename))
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        message = f"could not read {filename}: {err}"
        raise ValueError(message) from err
