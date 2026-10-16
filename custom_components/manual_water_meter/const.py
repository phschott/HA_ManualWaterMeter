"""Constants for the Manual Water Meter integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "manual_water_meter"
STORAGE_VERSION = 1

# Config / options keys
CONF_NAME = "name"
CONF_REMINDER_DAYS = "reminder_days"

# Defaults
DEFAULT_NAME = "Water meter"
DEFAULT_REMINDER_DAYS = 30
MIN_REMINDER_DAYS = 1
MAX_REMINDER_DAYS = 365

# Meter reading bounds (m³)
METER_MIN = 0
METER_MAX = 9999
METER_STEP = 0.001

# Dispatcher signal (suffixed with the entry id at runtime)
SIGNAL_UPDATE = f"{DOMAIN}_update"

# Event fired when a reading is overdue
EVENT_REMINDER = f"{DOMAIN}_reminder"

PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]
