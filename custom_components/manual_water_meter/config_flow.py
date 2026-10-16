"""Config and options flow for Manual Water Meter."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_NAME,
    CONF_REMINDER_DAYS,
    DEFAULT_NAME,
    DEFAULT_REMINDER_DAYS,
    DOMAIN,
    MAX_REMINDER_DAYS,
    MIN_REMINDER_DAYS,
)

_REMINDER_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_REMINDER_DAYS,
        max=MAX_REMINDER_DAYS,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="days",
    )
)


class ManualWaterMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user setup step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={},
                options={CONF_REMINDER_DAYS: int(user_input[CONF_REMINDER_DAYS])},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(
                    CONF_REMINDER_DAYS, default=DEFAULT_REMINDER_DAYS
                ): _REMINDER_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,  # noqa: ARG004
    ) -> ManualWaterMeterOptionsFlow:
        """Return the options flow handler."""
        return ManualWaterMeterOptionsFlow()


class ManualWaterMeterOptionsFlow(OptionsFlow):
    """Handle reminder-frequency changes."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_REMINDER_DAYS: int(user_input[CONF_REMINDER_DAYS])}
            )

        current = self.config_entry.options.get(
            CONF_REMINDER_DAYS, DEFAULT_REMINDER_DAYS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_REMINDER_DAYS, default=current): _REMINDER_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
