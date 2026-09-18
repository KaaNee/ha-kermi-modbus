"""Config flow for Kermi (Modbus).

Validates the connection with *temporary* Modbus units before the config
entry exists (``async_get_temporary_unit`` — see the 2026.9 "Modernizing
Modbus" docs), one per configured unit ID (x-center always; heating-circuit/
DHW storage modules only if given) — all on the same host/port, sharing one
underlying TCP connection (see ``homeassistant.components.modbus.connection``
— ``async_get_temporary_unit``/``async_get_unit`` key their shared connection
pool by endpoint, not by unit ID).

Unlike ``e3dc_modbus``, there is no ``KermiDevice.async_probe()`` to lean on
here: Kermi documents no model/serial-identification register anywhere (see
``kermi_modbus.models._base`` docstring), so this flow can only confirm that
something answers on each configured unit ID, not which model it is. The
unique ID is therefore derived from host/port/x-center-unit instead of a
device serial number.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from modbus_connection import ModbusTcpParams
from modbus_connection.exceptions import ModbusError

from kermi_modbus.models import XChangeDynamicProProfile

from .const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    CONF_PV_ENABLED,
    CONF_XCENTER_UNIT,
    DEFAULT_DHW_UNIT,
    DEFAULT_HEATING_CIRCUIT_UNIT,
    DEFAULT_PORT,
    DEFAULT_PV_ENABLED,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEFAULT_XCENTER_UNIT,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL_SECONDS,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT): int,
        vol.Required(CONF_XCENTER_UNIT): int,
        # Genuinely optional (no schema default): a heat pump without a
        # matching storage-module unit configured here just gets no
        # heating-circuit/DHW device — see kermi_modbus.KermiDevice, which
        # accepts either as None. Suggested values (50/51) are attached in
        # async_step_user instead of baked into the schema, so clearing the
        # field actually omits it.
        vol.Optional(CONF_HEATING_CIRCUIT_UNIT): int,
        vol.Optional(CONF_DHW_UNIT): int,
    }
)

_SUGGESTED_VALUES = {
    CONF_PORT: DEFAULT_PORT,
    CONF_XCENTER_UNIT: DEFAULT_XCENTER_UNIT,
    CONF_HEATING_CIRCUIT_UNIT: DEFAULT_HEATING_CIRCUIT_UNIT,
    CONF_DHW_UNIT: DEFAULT_DHW_UNIT,
}


async def _probe_unit(hass: object, params: ModbusTcpParams, unit_id: int, address: int) -> None:
    """Confirm something answers on ``unit_id`` — read one single register.

    A single-register read, not a batched multi-register Component read:
    confirmed the hard way against real hardware (2026-09-14) that reading a
    3-register block anchored on an address only valid for one domain (e.g.
    ``EnergySource``'s registers 1-3, x-center-only) gets a genuinely SHORT
    response from a storage-module unit — "Invalid register count: expected
    3, got 2" — not silently-zero-filled data. Kermi's storage-module units
    do return silent 0/default values for reads *within* the documented
    address range but on the "wrong" domain's unit (project plan §10.1); an
    address with no register at all behind it on that unit is a different
    case. Each call site below passes an address genuinely valid for that
    unit's own domain, so this only proves connectivity — not that the
    configured unit ID is actually the right domain.
    """
    async with async_get_temporary_unit(hass, params, unit_id) as unit:
        await unit.read_holding_registers(address, 1)


class KermiModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kermi (Modbus)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """First (and only) step: host/port/unit IDs, then probe each unit."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # No framer argument: a Modbus TCP link is always MBAP-framed
            # (modbus_connection deprecated the "socket" framer value for
            # ModbusTcpParams for exactly this reason).
            params = ModbusTcpParams(host=user_input[CONF_HOST], port=user_input[CONF_PORT])
            try:
                # 200 = x-center global state, 150 = heating-circuit status,
                # 100 = DHW actual temperature — one single register per
                # domain, each confirmed against real hardware this project
                # (see kermi-modbus's project plan §6.1/§10.1).
                await _probe_unit(self.hass, params, user_input[CONF_XCENTER_UNIT], address=200)
                if (heating_circuit_unit := user_input.get(CONF_HEATING_CIRCUIT_UNIT)) is not None:
                    await _probe_unit(self.hass, params, heating_circuit_unit, address=150)
                if (dhw_unit := user_input.get(CONF_DHW_UNIT)) is not None:
                    await _probe_unit(self.hass, params, dhw_unit, address=100)
            except (ModbusError, HomeAssistantError) as exception:
                # HomeAssistantError here means another entry already holds
                # this host/port with different link settings (see
                # async_get_temporary_unit's docstring) — surfaced the same
                # way as a plain connection failure, since the fix (matching
                # settings, or picking the right existing entry) is the
                # user's to make either way.
                LOGGER.warning("Could not reach Kermi device: %s", exception)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}_{user_input[CONF_XCENTER_UNIT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Kermi {XChangeDynamicProProfile.name}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, {**_SUGGESTED_VALUES, **(user_input or {})}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004 - required by the base signature
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return KermiModbusOptionsFlow()


class KermiModbusOptionsFlow(config_entries.OptionsFlow):
    """Options: PV-modulation opt-in + poll interval (project plan §9 Phase 2)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Single step: PV-modulation toggle + update interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_PV_ENABLED,
                    default=self.config_entry.options.get(CONF_PV_ENABLED, DEFAULT_PV_ENABLED),
                ): bool,
                vol.Required(
                    "update_interval_seconds",
                    default=self.config_entry.options.get(
                        "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS
                    ),
                ): vol.All(int, vol.Range(min=MIN_UPDATE_INTERVAL_SECONDS)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=options_schema)
