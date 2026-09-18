"""Number platform for Kermi (Modbus): writable numeric setpoints.

Covers 9 of the 15 documented writable registers (project plan §9 Phase 2);
the enum-typed writable registers are ``select.py``, the boolean one is
``switch.py``. Min/max/step come from the Excel's documented range where
``kermi_modbus``'s ``const.py`` has one; write-time enforcement of that same
range already happens in the device library itself
(``kermi_modbus.validation.range_validator``, wired into each writable
field) — the values here are only the UI's slider/box bounds, not a
second, independent safety check.

The two PV-modulation setpoints (302/303) are the one exception: Kermi's
own Excel documents no Min/Max for them (only a default of 50°C), so
``kermi_modbus`` wires no range validator for those two fields either — the
bounds below are a conservative UI guardrail this integration chose, not a
manufacturer-documented range, and a write outside them still reaches the
device unvalidated at the library level.

After a write, each entity re-reads just its own component directly
(``component.async_update()``) instead of calling
``coordinator.async_request_refresh()`` — confirmed (2026-09-14, test suite)
that the coordinator's refresh debounces with a 10-second cooldown
(``REQUEST_REFRESH_DEFAULT_COOLDOWN``), so two writes within 10s of each
other would leave an entity showing the *first* write's value until the
coordinator's next natural poll.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature

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

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from kermi_modbus import KermiDevice

    from .coordinator import KermiModbusDataUpdateCoordinator
    from .data import KermiModbusConfigEntry


@dataclass(frozen=True, kw_only=True)
class KermiNumberEntityDescription(NumberEntityDescription):
    """Number description bound to one writable field on a Kermi component."""

    device_key: str
    component_fn: Callable[[KermiDevice], Any]
    field: str


DHW_NUMBERS: tuple[KermiNumberEntityDescription, ...] = (
    KermiNumberEntityDescription(
        key="dhw_constant_setpoint",
        translation_key="dhw_constant_setpoint",
        device_key=DEVICE_KEY_DHW,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=85,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.dhw_module.dhw,
        field="constant_setpoint",
    ),
    KermiNumberEntityDescription(
        key="dhw_single_charge_setpoint",
        translation_key="dhw_single_charge_setpoint",
        device_key=DEVICE_KEY_DHW,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=30,
        native_max_value=60,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.dhw_module.dhw,
        field="single_charge_setpoint",
    ),
)

HEATING_CIRCUIT_NUMBERS: tuple[KermiNumberEntityDescription, ...] = (
    KermiNumberEntityDescription(
        key="heating_curve_parallel_shift",
        translation_key="heating_curve_parallel_shift",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-5,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="heating_curve_parallel_shift",
    ),
    KermiNumberEntityDescription(
        key="summer_mode_off_threshold",
        translation_key="summer_mode_off_threshold",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="summer_mode_off_threshold",
    ),
    KermiNumberEntityDescription(
        key="winter_mode_on_threshold",
        translation_key="winter_mode_on_threshold",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="winter_mode_on_threshold",
    ),
    KermiNumberEntityDescription(
        key="cooling_mode_on_threshold",
        translation_key="cooling_mode_on_threshold",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="cooling_mode_on_threshold",
    ),
    KermiNumberEntityDescription(
        key="cooling_mode_off_threshold",
        translation_key="cooling_mode_off_threshold",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=50,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="cooling_mode_off_threshold",
    ),
)

# UNDOCUMENTED range (see module docstring) — Kermi's Excel gives no Min/Max
# for these two, only a default of 50°C. Only added when PV modulation is
# enabled (options flow), since device.xcenter.pv_modulation is None
# otherwise.
PV_MODULATION_NUMBERS: tuple[KermiNumberEntityDescription, ...] = (
    KermiNumberEntityDescription(
        key="pv_target_temperature_heating",
        translation_key="pv_target_temperature_heating",
        device_key=DEVICE_KEY_XCENTER,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=85,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.xcenter.pv_modulation,
        field="target_temperature_heating",
    ),
    KermiNumberEntityDescription(
        key="pv_target_temperature_dhw",
        translation_key="pv_target_temperature_dhw",
        device_key=DEVICE_KEY_XCENTER,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=85,
        native_step=0.1,
        mode=NumberMode.BOX,
        component_fn=lambda device: device.xcenter.pv_modulation,
        field="target_temperature_dhw",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required by the platform signature
    entry: KermiModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable numeric setpoints for one config entry."""
    coordinator = entry.runtime_data.coordinator
    descriptions: list[KermiNumberEntityDescription] = []
    if entry.data.get(CONF_HEATING_CIRCUIT_UNIT) is not None:
        descriptions.extend(HEATING_CIRCUIT_NUMBERS)
    if entry.data.get(CONF_DHW_UNIT) is not None:
        descriptions.extend(DHW_NUMBERS)
    if entry.runtime_data.device.xcenter.pv_modulation is not None:
        descriptions.extend(PV_MODULATION_NUMBERS)

    async_add_entities(KermiModbusNumber(coordinator, description) for description in descriptions)


class KermiModbusNumber(KermiModbusEntity, NumberEntity):
    """A single writable Kermi setpoint."""

    entity_description: KermiNumberEntityDescription

    def __init__(
        self,
        coordinator: KermiModbusDataUpdateCoordinator,
        entity_description: KermiNumberEntityDescription,
    ) -> None:
        """Bind this number to its description and a stable unique ID."""
        super().__init__(coordinator, entity_description.device_key)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.device_key}_{entity_description.key}"
        )

    @property
    def native_value(self) -> float | None:
        """Current setpoint, read live off the device object graph."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        return getattr(component, self.entity_description.field)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new setpoint, then read it straight back and push it.

        Not ``coordinator.async_request_refresh()``: that debounces with a
        10-second cooldown (see module docstring), which would leave this
        entity showing a stale value after two writes in quick succession.
        """
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        await component.write(self.entity_description.field, value)
        await component.async_update()
        self.async_write_ha_state()
