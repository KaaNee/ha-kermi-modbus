"""Sensor platform for Kermi (Modbus).

Read-only fields only, for every configured device (project plan §10.1: up
to three — x-center always, heating-circuit/DHW storage modules if
configured). Writable registers (setpoints, operating modes, thresholds) are
deliberately NOT exposed here — they become ``number``/``select``/``switch``
entities in a follow-up (see project plan §9 Phase 2), so no entity_id ever
has to move from ``sensor`` to a control platform.

Every sensor reads straight off ``entry.runtime_data.device`` (updated by the
coordinator) via ``value_fn`` — there's no intermediate dict, since
``kermi_modbus``'s blocks are already the live, mutable state.

Electrical vs. thermal power (project plan, Energy Dashboard investigation):
addresses 104-107 ("Aktuelle Leistung") are the heat pump's THERMAL output,
paired with the COP registers (100-103) — COP = thermal / electrical, so both
sides must exist. Addresses 108-111 ("Elektr. Leistung") are the ELECTRICAL
input. Only the electrical-power sensors are valid input for HA's Energy
Dashboard (via the built-in "Integration - Riemann sum" helper, see the root
README) — feeding a thermal-power sensor into that helper overstates real
grid consumption by roughly the COP. Translation keys are prefixed
``thermal_power``/``electric_power`` specifically so this distinction is
visible in the entity names, not just in this comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower, UnitOfTemperature, UnitOfTime, UnitOfVolumeFlowRate

from kermi_modbus.enums import (
    ExternalHeatGeneratorStatus,
    GlobalState,
    HeatingCircuitStatus,
    OperatingMode,
)

from .const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    DEVICE_KEY_DHW,
    DEVICE_KEY_HEATING_CIRCUIT,
    DEVICE_KEY_XCENTER,
)
from .entity import KermiModbusEntity

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import IntEnum

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from kermi_modbus import KermiDevice

    from .coordinator import KermiModbusDataUpdateCoordinator
    from .data import KermiModbusConfigEntry


def _enum_key(value: IntEnum | None) -> str | None:
    """Map an IntEnum member to its lowercase name, or ``None`` through.

    ``kermi_modbus``'s ``enum()`` fields already decode an undocumented raw
    value as ``None`` with a logged warning (see kermi-modbus's const.py) —
    never as an out-of-``options`` string, which ``SensorDeviceClass.ENUM``
    would reject.
    """
    return value.name.lower() if value is not None else None


@dataclass(frozen=True, kw_only=True)
class KermiSensorEntityDescription(SensorEntityDescription):
    """Sensor description bound to a value getter on ``KermiDevice``."""

    device_key: str
    value_fn: Callable[[KermiDevice], float | int | str | None]


XCENTER_SENSORS: tuple[KermiSensorEntityDescription, ...] = (
    # --- Energiequelle (100-103 excluded: COP, see below) ------------------
    KermiSensorEntityDescription(
        key="exit_temperature",
        translation_key="exit_temperature",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.xcenter.energy_source.exit_temperature,
    ),
    KermiSensorEntityDescription(
        key="incoming_temperature",
        translation_key="incoming_temperature",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.xcenter.energy_source.incoming_temperature,
    ),
    KermiSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.xcenter.energy_source.outside_temperature,
    ),
    # --- Ladekreis -----------------------------------------------------------
    KermiSensorEntityDescription(
        key="flow_temperature",
        translation_key="flow_temperature",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.xcenter.charging_circuit.flow_temperature,
    ),
    KermiSensorEntityDescription(
        key="return_temperature",
        translation_key="return_temperature",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.xcenter.charging_circuit.return_temperature,
    ),
    KermiSensorEntityDescription(
        key="flow_speed",
        translation_key="flow_speed",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        value_fn=lambda device: device.xcenter.charging_circuit.flow_speed,
    ),
    # --- Leistung und Effizienz: COP (dimensionless) ------------------------
    KermiSensorEntityDescription(
        key="cop",
        translation_key="cop",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.xcenter.power.cop,
    ),
    KermiSensorEntityDescription(
        key="cop_heating",
        translation_key="cop_heating",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.xcenter.power.cop_heating,
    ),
    KermiSensorEntityDescription(
        key="cop_dhw",
        translation_key="cop_dhw",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.xcenter.power.cop_dhw,
    ),
    KermiSensorEntityDescription(
        key="cop_cooling",
        translation_key="cop_cooling",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.xcenter.power.cop_cooling,
    ),
    # --- Leistung: THERMAL output (104-107) — NOT valid for the Energy
    # Dashboard, see module docstring. -----------------------------------
    KermiSensorEntityDescription(
        key="thermal_power",
        translation_key="thermal_power",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.power,
    ),
    KermiSensorEntityDescription(
        key="thermal_power_heating",
        translation_key="thermal_power_heating",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.power_heating,
    ),
    KermiSensorEntityDescription(
        key="thermal_power_dhw",
        translation_key="thermal_power_dhw",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.power_dhw,
    ),
    KermiSensorEntityDescription(
        key="thermal_power_cooling",
        translation_key="thermal_power_cooling",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.power_cooling,
    ),
    # --- Leistung: ELECTRICAL input (108-111) — the valid Energy Dashboard
    # input, via HA's own Riemann-sum helper. See module docstring. ---------
    KermiSensorEntityDescription(
        key="electric_power",
        translation_key="electric_power",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.electric_power,
    ),
    KermiSensorEntityDescription(
        key="electric_power_heating",
        translation_key="electric_power_heating",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.electric_power_heating,
    ),
    KermiSensorEntityDescription(
        key="electric_power_dhw",
        translation_key="electric_power_dhw",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.electric_power_dhw,
    ),
    KermiSensorEntityDescription(
        key="electric_power_cooling",
        translation_key="electric_power_cooling",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda device: device.xcenter.power.electric_power_cooling,
    ),
    # --- Betriebsstunden: lifetime runtime counters. TOTAL_INCREASING, not
    # MEASUREMENT — these only ever go up (or wrap/reset), which is exactly
    # what that state class is for; kermi-modbus's own Register metadata says
    # "measurement" but that's documentation-only (see its const.py), not
    # binding on this HA-layer choice. ---------------------------------------
    KermiSensorEntityDescription(
        key="compressor_work_hours",
        translation_key="compressor_work_hours",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda device: device.xcenter.work_hours.compressor,
    ),
    KermiSensorEntityDescription(
        key="fan_work_hours",
        translation_key="fan_work_hours",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda device: device.xcenter.work_hours.fan,
    ),
    KermiSensorEntityDescription(
        key="storage_loading_pump_work_hours",
        translation_key="storage_loading_pump_work_hours",
        device_key=DEVICE_KEY_XCENTER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda device: device.xcenter.work_hours.storage_loading_pump,
    ),
    # --- Status --------------------------------------------------------------
    KermiSensorEntityDescription(
        key="global_state",
        translation_key="global_state",
        device_key=DEVICE_KEY_XCENTER,
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in GlobalState],
        value_fn=lambda device: _enum_key(device.xcenter.state.global_state),
    ),
)

# Only added when PV modulation is enabled (options flow) — the field
# doesn't exist on the device object otherwise (device.xcenter.pv_modulation
# is None), so this can't be a plain entity_registry_enabled_default=False
# entry like e3dc_modbus's wallbox sensors.
PV_MODULATION_POWER_SENSOR = KermiSensorEntityDescription(
    key="pv_modulation_power",
    translation_key="pv_modulation_power",
    device_key=DEVICE_KEY_XCENTER,
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
    value_fn=lambda device: device.xcenter.pv_modulation.power,
)

HEATING_CIRCUIT_SENSORS: tuple[KermiSensorEntityDescription, ...] = (
    KermiSensorEntityDescription(
        key="buffer_actual_temperature",
        translation_key="buffer_actual_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.buffer.actual_temperature,
    ),
    KermiSensorEntityDescription(
        key="buffer_target_temperature",
        translation_key="buffer_target_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.buffer.target_temperature,
    ),
    KermiSensorEntityDescription(
        key="cooling_buffer_actual_temperature",
        translation_key="cooling_buffer_actual_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.cooling_buffer.actual_temperature,
    ),
    KermiSensorEntityDescription(
        key="cooling_buffer_target_temperature",
        translation_key="cooling_buffer_target_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.cooling_buffer.target_temperature,
    ),
    KermiSensorEntityDescription(
        key="heating_circuit_status",
        translation_key="heating_circuit_status",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in HeatingCircuitStatus],
        value_fn=lambda device: _enum_key(device.heating_circuit_module.heating_circuit.status),
    ),
    KermiSensorEntityDescription(
        key="heating_circuit_actual_temperature",
        translation_key="heating_circuit_actual_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.heating_circuit.actual_temperature,
    ),
    KermiSensorEntityDescription(
        key="heating_circuit_target_temperature",
        translation_key="heating_circuit_target_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.heating_circuit.target_temperature,
    ),
    KermiSensorEntityDescription(
        key="operating_mode",
        translation_key="operating_mode",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in OperatingMode],
        value_fn=lambda device: _enum_key(
            device.heating_circuit_module.heating_circuit.operating_mode
        ),
    ),
    KermiSensorEntityDescription(
        key="external_heat_generator_status",
        translation_key="external_heat_generator_status",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in ExternalHeatGeneratorStatus],
        value_fn=lambda device: _enum_key(
            device.heating_circuit_module.external_heat_generator.status
        ),
    ),
    KermiSensorEntityDescription(
        key="probe_1",
        translation_key="probe",
        translation_placeholders={"index": "1"},
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.heating_circuit_module.sensors.probe_1,
    ),
    KermiSensorEntityDescription(
        key="probe_2",
        translation_key="probe",
        translation_placeholders={"index": "2"},
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.heating_circuit_module.sensors.probe_2,
    ),
    KermiSensorEntityDescription(
        key="probe_3",
        translation_key="probe",
        translation_placeholders={"index": "3"},
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.heating_circuit_module.sensors.probe_3,
    ),
    KermiSensorEntityDescription(
        key="probe_4",
        translation_key="probe",
        translation_placeholders={"index": "4"},
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.heating_circuit_module.sensors.probe_4,
    ),
    KermiSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.sensors.outside_temperature,
    ),
    KermiSensorEntityDescription(
        key="outside_temperature_averaged",
        translation_key="outside_temperature_averaged",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.heating_circuit_module.sensors.outside_temperature_averaged,
    ),
    KermiSensorEntityDescription(
        key="heating_circuit_pump_work_hours",
        translation_key="heating_circuit_pump_work_hours",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda device: device.heating_circuit_module.work_hours.heating_circuit_pump,
    ),
    KermiSensorEntityDescription(
        key="heating_rod_work_hours",
        translation_key="heating_rod_work_hours",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda device: device.heating_circuit_module.work_hours.heating_rod,
    ),
)

DHW_SENSORS: tuple[KermiSensorEntityDescription, ...] = (
    KermiSensorEntityDescription(
        key="dhw_actual_temperature",
        translation_key="dhw_actual_temperature",
        device_key=DEVICE_KEY_DHW,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.dhw_module.dhw.actual_temperature,
    ),
    KermiSensorEntityDescription(
        key="dhw_target_temperature",
        translation_key="dhw_target_temperature",
        device_key=DEVICE_KEY_DHW,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device: device.dhw_module.dhw.target_temperature,
    ),
    KermiSensorEntityDescription(
        key="external_heat_generator_status",
        translation_key="external_heat_generator_status",
        device_key=DEVICE_KEY_DHW,
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in ExternalHeatGeneratorStatus],
        value_fn=lambda device: _enum_key(device.dhw_module.external_heat_generator.status),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required by the platform signature
    entry: KermiModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for one config entry."""
    coordinator = entry.runtime_data.coordinator
    descriptions = list(XCENTER_SENSORS)
    if entry.runtime_data.device.xcenter.pv_modulation is not None:
        descriptions.append(PV_MODULATION_POWER_SENSOR)
    if entry.data.get(CONF_HEATING_CIRCUIT_UNIT) is not None:
        descriptions.extend(HEATING_CIRCUIT_SENSORS)
    if entry.data.get(CONF_DHW_UNIT) is not None:
        descriptions.extend(DHW_SENSORS)

    async_add_entities(KermiModbusSensor(coordinator, description) for description in descriptions)


class KermiModbusSensor(KermiModbusEntity, SensorEntity):
    """A single read-only Kermi value."""

    entity_description: KermiSensorEntityDescription

    def __init__(
        self,
        coordinator: KermiModbusDataUpdateCoordinator,
        entity_description: KermiSensorEntityDescription,
    ) -> None:
        """Bind this sensor to its description and a stable unique ID."""
        super().__init__(coordinator, entity_description.device_key)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.device_key}_{entity_description.key}"
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Current value, read live off the device object graph."""
        return self.entity_description.value_fn(self.coordinator.config_entry.runtime_data.device)
