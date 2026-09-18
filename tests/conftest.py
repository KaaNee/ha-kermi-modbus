"""Shared fixtures for kermi_modbus tests."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusConnection, MockModbusUnit

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_kermi_units() -> dict[int, MockModbusUnit]:
    """Mock units for x-center (40) + heating-circuit (50) + DHW (51).

    Keyed by unit ID.
    """
    conn = MockModbusConnection()
    xcenter = conn.for_unit(40)
    heating_circuit = conn.for_unit(50)
    dhw = conn.for_unit(51)

    # x-center: outside 8.0 °C, flow/return 45.0/40.0 °C, COP 3.5, thermal
    # 8.0 kW, electrical 2.3 kW, standby.
    xcenter.holding[1] = 45  # exit_temperature: 4.5 °C
    xcenter.holding[2] = 40  # incoming_temperature: 4.0 °C
    xcenter.holding[3] = 80  # outside_temperature: 8.0 °C
    xcenter.holding[50] = 450  # flow_temperature: 45.0 °C
    xcenter.holding[51] = 400  # return_temperature: 40.0 °C
    xcenter.holding[52] = 120  # flow_speed: 12.0 l/min
    xcenter.holding[100] = 35  # cop: 3.5
    xcenter.holding[104] = 80  # thermal power: 8.0 kW
    xcenter.holding[108] = 23  # electric power: 2.3 kW
    xcenter.holding[152] = 59290  # compressor work hours raw: 5929.0 h
    xcenter.holding[200] = 0  # global_state: STANDBY
    xcenter.holding[250] = 0  # alarm.active: False

    # Heating-circuit module (unit 50): heating, buffer 42.0/45.0 °C.
    heating_circuit.holding[1] = 420  # buffer.actual_temperature: 42.0 °C
    heating_circuit.holding[2] = 450  # buffer.target_temperature: 45.0 °C
    heating_circuit.holding[150] = 1  # heating_circuit.status: HEATING
    heating_circuit.holding[151] = 350  # heating_circuit.actual_temperature: 35.0 °C
    heating_circuit.holding[153] = 1  # operating_mode: HEATING
    heating_circuit.holding[154] = 0  # operating_type: AUTO (writable)
    heating_circuit.holding[155] = 2  # energy_mode: NORMAL (writable)
    heating_circuit.holding[156] = (-3) & 0xFFFF  # heating_curve_parallel_shift: -3 (writable)
    heating_circuit.holding[157] = 0  # manual_season_selection: AUTO (writable)
    heating_circuit.holding[158] = 180  # summer_mode_off_threshold: 18.0 °C (writable)
    heating_circuit.holding[159] = 160  # winter_mode_on_threshold: 16.0 °C (writable)
    heating_circuit.holding[160] = 220  # cooling_mode_on_threshold: 22.0 °C (writable)
    heating_circuit.holding[161] = 200  # cooling_mode_off_threshold: 20.0 °C (writable)
    heating_circuit.holding[200] = 0  # external_heat_generator.status: NO_REQUEST
    heating_circuit.holding[201] = 0  # external_heat_generator.mode: AUTO (writable)

    # DHW module (unit 51): 48.5 °C actual, 50.0 °C target.
    dhw.holding[100] = 485  # dhw.actual_temperature: 48.5 °C
    dhw.holding[101] = 500  # dhw.target_temperature: 50.0 °C
    dhw.holding[102] = 550  # constant_setpoint: 55.0 °C (writable)
    dhw.holding[103] = 0  # single_charge: False (writable)
    dhw.holding[104] = 500  # single_charge_setpoint: 50.0 °C (writable)
    dhw.holding[202] = 0  # external_heat_generator.status: NO_REQUEST
    dhw.holding[203] = 0  # external_heat_generator.mode: AUTO (writable)

    return {40: xcenter, 50: heating_circuit, 51: dhw}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # noqa: ARG001
    """Make custom_components/ discoverable in every test automatically."""
    return
