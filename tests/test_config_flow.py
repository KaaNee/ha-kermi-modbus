"""Test the config flow.

``async_get_temporary_unit`` itself belongs to HA core's ``modbus`` component
(real TCP connection handling) — not our code, so it's mocked here, once per
configured unit ID (x-center always, heating-circuit/DHW only if given).
Everything downstream (error mapping, unique_id, entry creation) is our code
and is exercised for real.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from modbus_connection.exceptions import ModbusTimeoutError

from custom_components.kermi_modbus.const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    CONF_XCENTER_UNIT,
    DOMAIN,
)


def _get_temporary_unit_from(units_by_id):
    @asynccontextmanager
    async def _get(hass, params, unit_id):  # noqa: ARG001
        yield units_by_id[unit_id]

    return _get


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_kermi_units) -> None:
    """A reachable x-center + both storage modules creates a config entry."""
    with patch(
        "custom_components.kermi_modbus.config_flow.async_get_temporary_unit",
        side_effect=_get_temporary_unit_from(mock_kermi_units),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "kermi.example",
                CONF_PORT: 502,
                CONF_XCENTER_UNIT: 40,
                CONF_HEATING_CIRCUIT_UNIT: 50,
                CONF_DHW_UNIT: 51,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kermi x-change dynamic pro"
    assert result["data"][CONF_XCENTER_UNIT] == 40
    assert result["data"][CONF_HEATING_CIRCUIT_UNIT] == 50
    assert result["data"][CONF_DHW_UNIT] == 51


async def test_user_flow_xcenter_only(hass: HomeAssistant, mock_kermi_units) -> None:
    """Heating-circuit/DHW units are genuinely optional."""
    with patch(
        "custom_components.kermi_modbus.config_flow.async_get_temporary_unit",
        side_effect=_get_temporary_unit_from(mock_kermi_units),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "kermi.example", CONF_PORT: 502, CONF_XCENTER_UNIT: 40},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_HEATING_CIRCUIT_UNIT not in result["data"]
    assert CONF_DHW_UNIT not in result["data"]


async def test_user_flow_duplicate_endpoint_aborts(hass: HomeAssistant, mock_kermi_units) -> None:
    """A second entry for the same host/port/x-center unit is refused."""
    with patch(
        "custom_components.kermi_modbus.config_flow.async_get_temporary_unit",
        side_effect=_get_temporary_unit_from(mock_kermi_units),
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(
            first["flow_id"],
            {CONF_HOST: "kermi.example", CONF_PORT: 502, CONF_XCENTER_UNIT: 40},
        )

        second = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            second["flow_id"],
            {CONF_HOST: "kermi.example", CONF_PORT: 502, CONF_XCENTER_UNIT: 40},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_connection_error(hass: HomeAssistant) -> None:
    """An unreachable device shows a form error instead of crashing the flow."""

    @asynccontextmanager
    async def _raise(*_args, **_kwargs):
        raise ModbusTimeoutError("no response")
        yield  # pragma: no cover - unreachable, satisfies the generator shape

    with patch(
        "custom_components.kermi_modbus.config_flow.async_get_temporary_unit",
        side_effect=_raise,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "kermi.example", CONF_PORT: 502, CONF_XCENTER_UNIT: 40},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
