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

# Statistics import service
SERVICE_IMPORT_HISTORY = "import_history"
ATTR_FILENAME = "filename"
ATTR_CSV = "csv"
ATTR_UPDATE_CURRENT = "update_current"

# Source tag required by the recorder for entity-backed statistics
RECORDER_SOURCE = "recorder"
# Minimum columns / rows expected in a history CSV
MIN_CSV_COLUMNS = 2
MIN_READINGS = 2

PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

# Reminder notification texts, keyed by language (falls back to English).
# {name} and {days} are substituted at runtime.
DEFAULT_LANGUAGE = "en"
NOTIFICATION_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Water meter reading due — {name}",
        "message_never": (
            "No reading has ever been recorded for '{name}'. "
            "Please enter your current water meter value."
        ),
        "message_overdue": (
            "It has been {days} day(s) since the last reading of '{name}'. "
            "Please update your water meter value."
        ),
    },
    "fr": {
        "title": "Relevé du compteur d'eau à faire — {name}",
        "message_never": (
            "Aucun relevé n'a encore été enregistré pour « {name} ». "
            "Veuillez saisir la valeur actuelle de votre compteur d'eau."
        ),
        "message_overdue": (
            "Cela fait {days} jour(s) depuis le dernier relevé de « {name} ». "
            "Veuillez mettre à jour la valeur de votre compteur d'eau."
        ),
    },
}
