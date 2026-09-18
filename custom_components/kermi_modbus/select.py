"""Select platform for Kermi (Modbus): writable enum-typed registers.

Covers 5 of the 15 documented writable registers (project plan §9 Phase 2).
No range validator is needed here the way ``number.py`` needs one: writing
through the enum's own Python type (``EnumClass[option.upper()]``) already
constrains the value to a documented member — see kermi-modbus's
``validation.py`` module docstring, which states this explicitly.

After a write, each entity re-reads just its own component directly
(``component.async_update()``) instead of calling
``coordinator.async_request_refresh()`` — see ``number.py``'s module
docstring for why (the coordinator's refresh debounces with a 10-second
cooldown).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription

from kermi_modbus.enums import EnergyMode, ExternalHeatGeneratorMode, OperatingType, SeasonSelection

from .const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    DEVICE_KEY_DHW,
    DEVICE_KEY_HEATING_CIRCUIT,
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


@dataclass(frozen=True, kw_only=True)
class KermiSelectEntityDescription(SelectEntityDescription):
    """Select description bound to one writable enum field on a Kermi component."""

    device_key: str
    enum_type: type[IntEnum]
    component_fn: Callable[[KermiDevice], Any]
    field: str


HEATING_CIRCUIT_SELECTS: tuple[KermiSelectEntityDescription, ...] = (
    KermiSelectEntityDescription(
        key="operating_type",
        translation_key="operating_type_select",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        enum_type=OperatingType,
        options=[member.name.lower() for member in OperatingType],
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="operating_type",
    ),
    KermiSelectEntityDescription(
        key="energy_mode",
        translation_key="energy_mode_select",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        enum_type=EnergyMode,
        options=[member.name.lower() for member in EnergyMode],
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="energy_mode",
    ),
    KermiSelectEntityDescription(
        key="manual_season_selection",
        translation_key="manual_season_selection_select",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        enum_type=SeasonSelection,
        options=[member.name.lower() for member in SeasonSelection],
        component_fn=lambda device: device.heating_circuit_module.heating_circuit,
        field="manual_season_selection",
    ),
    KermiSelectEntityDescription(
        key="external_heat_generator_mode",
        translation_key="external_heat_generator_mode_select",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        enum_type=ExternalHeatGeneratorMode,
        options=[member.name.lower() for member in ExternalHeatGeneratorMode],
        component_fn=lambda device: device.heating_circuit_module.external_heat_generator,
        field="mode",
    ),
)

DHW_SELECTS: tuple[KermiSelectEntityDescription, ...] = (
    KermiSelectEntityDescription(
        key="external_heat_generator_mode",
        translation_key="external_heat_generator_mode_select",
        device_key=DEVICE_KEY_DHW,
        enum_type=ExternalHeatGeneratorMode,
        options=[member.name.lower() for member in ExternalHeatGeneratorMode],
        component_fn=lambda device: device.dhw_module.external_heat_generator,
        field="mode",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required by the platform signature
    entry: KermiModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable enum selects for one config entry."""
    coordinator = entry.runtime_data.coordinator
    descriptions: list[KermiSelectEntityDescription] = []
    if entry.data.get(CONF_HEATING_CIRCUIT_UNIT) is not None:
        descriptions.extend(HEATING_CIRCUIT_SELECTS)
    if entry.data.get(CONF_DHW_UNIT) is not None:
        descriptions.extend(DHW_SELECTS)

    async_add_entities(KermiModbusSelect(coordinator, description) for description in descriptions)


class KermiModbusSelect(KermiModbusEntity, SelectEntity):
    """A single writable Kermi enum-typed register."""

    entity_description: KermiSelectEntityDescription

    def __init__(
        self,
        coordinator: KermiModbusDataUpdateCoordinator,
        entity_description: KermiSelectEntityDescription,
    ) -> None:
        """Bind this select to its description and a stable unique ID."""
        super().__init__(coordinator, entity_description.device_key)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.device_key}_{entity_description.key}"
        )

    @property
    def current_option(self) -> str | None:
        """Current enum member, read live off the device object graph."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        value = getattr(component, self.entity_description.field)
        return value.name.lower() if value is not None else None

    async def async_select_option(self, option: str) -> None:
        """Write the selected enum member, then read it straight back and push it."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        member = self.entity_description.enum_type[option.upper()]
        await component.write(self.entity_description.field, member)
        await component.async_update()
        self.async_write_ha_state()
