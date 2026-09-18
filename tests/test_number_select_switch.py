"""Test the writable platforms: number, select, switch.

Exercises a full config-entry setup (mocked Modbus connection) and drives
each platform through its real HA service call (``number.set_value``,
``select.select_option``, ``switch.turn_on``/``turn_off``) rather than
calling the entity methods directly — this is the same path a real user's
dashboard interaction takes.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kermi_modbus.const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    CONF_XCENTER_UNIT,
    DEVICE_KEY_DHW,
    DEVICE_KEY_HEATING_CIRCUIT,
    DOMAIN,
)

_ENTRY_DATA = {
    CONF_HOST: "kermi.example",
    CONF_PORT: 502,
    CONF_XCENTER_UNIT: 40,
    CONF_HEATING_CIRCUIT_UNIT: 50,
    CONF_DHW_UNIT: 51,
}


def _get_unit_from(units_by_id):
    def _get(hass, entry, params, unit_id):  # noqa: ARG001
        return units_by_id[unit_id]

    return _get


async def _setup_entry(hass: HomeAssistant, mock_kermi_units) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="kermi.example_502_40")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.kermi_modbus.async_get_unit",
        side_effect=_get_unit_from(mock_kermi_units),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry_id: str, platform: str, device_key: str, key: str) -> str:
    registry = er.async_get(hass)
    unique_id = f"{entry_id}_{device_key}_{key}"
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, f"no entity registered for unique_id={unique_id!r}"
    return entity_id


async def test_number_reads_and_writes_dhw_constant_setpoint(
    hass: HomeAssistant, mock_kermi_units
) -> None:
    """DHW constant setpoint (register 102) round-trips through the number platform."""
    entry = await _setup_entry(hass, mock_kermi_units)
    entity_id = _entity_id(hass, entry.entry_id, "number", DEVICE_KEY_DHW, "dhw_constant_setpoint")

    assert hass.states.get(entity_id).state == "55.0"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 52.5},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "52.5"
    assert mock_kermi_units[51].holding[102] == 525


async def test_select_reads_and_writes_energy_mode(hass: HomeAssistant, mock_kermi_units) -> None:
    """Energy mode (register 155) round-trips through the select platform."""
    entry = await _setup_entry(hass, mock_kermi_units)
    entity_id = _entity_id(
        hass, entry.entry_id, "select", DEVICE_KEY_HEATING_CIRCUIT, "energy_mode"
    )

    assert hass.states.get(entity_id).state == "normal"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: "comfort"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "comfort"
    assert mock_kermi_units[50].holding[155] == 3


async def test_switch_reads_and_writes_dhw_single_charge(
    hass: HomeAssistant, mock_kermi_units
) -> None:
    """DHW single-charge (register 103) round-trips through the switch platform."""
    entry = await _setup_entry(hass, mock_kermi_units)
    entity_id = _entity_id(hass, entry.entry_id, "switch", DEVICE_KEY_DHW, "dhw_single_charge")

    assert hass.states.get(entity_id).state == "off"

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"
    assert mock_kermi_units[51].holding[103] == 1

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"
    assert mock_kermi_units[51].holding[103] == 0
