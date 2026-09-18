"""Test setting up a config entry end to end (mocked Modbus connection).

Looks entities up by their known ``unique_id`` via the entity registry
rather than guessing the HA-generated ``entity_id`` slug — robust against
naming/translation changes, and the only reliable way when several devices
(x-center/heating-circuit/DHW) share one config entry.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kermi_modbus.const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    CONF_XCENTER_UNIT,
    DEVICE_KEY_DHW,
    DEVICE_KEY_HEATING_CIRCUIT,
    DEVICE_KEY_XCENTER,
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


def _state_for(hass: HomeAssistant, entry_id: str, device_key: str, key: str):
    registry = er.async_get(hass)
    unique_id = f"{entry_id}_{device_key}_{key}"
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None, f"no entity registered for unique_id={unique_id!r}"
    return hass.states.get(entity_id)


async def test_setup_entry_creates_expected_entities(hass: HomeAssistant, mock_kermi_units) -> None:
    """A full setup polls all three units once and creates entities for each."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="kermi.example_502_40")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kermi_modbus.async_get_unit",
        side_effect=_get_unit_from(mock_kermi_units),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    cop = _state_for(hass, entry.entry_id, DEVICE_KEY_XCENTER, "cop")
    assert cop is not None
    assert cop.state == "3.5"

    electric_power = _state_for(hass, entry.entry_id, DEVICE_KEY_XCENTER, "electric_power")
    assert electric_power is not None
    assert electric_power.state == "2.3"

    global_state = _state_for(hass, entry.entry_id, DEVICE_KEY_XCENTER, "global_state")
    assert global_state is not None
    assert global_state.state == "standby"

    heating_circuit_status = _state_for(
        hass, entry.entry_id, DEVICE_KEY_HEATING_CIRCUIT, "heating_circuit_status"
    )
    assert heating_circuit_status is not None
    assert heating_circuit_status.state == "heating"

    dhw_actual = _state_for(hass, entry.entry_id, DEVICE_KEY_DHW, "dhw_actual_temperature")
    assert dhw_actual is not None
    assert dhw_actual.state == "48.5"


async def test_setup_entry_without_storage_modules(hass: HomeAssistant, mock_kermi_units) -> None:
    """No heating-circuit/DHW device (and no entities for them) when unconfigured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "kermi.example", CONF_PORT: 502, CONF_XCENTER_UNIT: 40},
        unique_id="kermi.example_502_40",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kermi_modbus.async_get_unit",
        side_effect=_get_unit_from(mock_kermi_units),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    heating_circuit_unique_id = (
        f"{entry.entry_id}_{DEVICE_KEY_HEATING_CIRCUIT}_heating_circuit_status"
    )
    assert registry.async_get_entity_id("sensor", DOMAIN, heating_circuit_unique_id) is None

    dhw_unique_id = f"{entry.entry_id}_{DEVICE_KEY_DHW}_dhw_actual_temperature"
    assert registry.async_get_entity_id("sensor", DOMAIN, dhw_unique_id) is None


async def test_unload_entry(hass: HomeAssistant, mock_kermi_units) -> None:
    """Unloading a loaded entry succeeds and tears platforms down."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="kermi.example_502_40")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kermi_modbus.async_get_unit",
        side_effect=_get_unit_from(mock_kermi_units),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
