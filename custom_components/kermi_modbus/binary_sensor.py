"""Binary sensor platform for Kermi (Modbus): read-only status flags.

Writable bits (e.g. DHW single-charge) are excluded here on purpose — they
become ``switch`` entities in a follow-up, see sensor.py's module docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import CONF_HEATING_CIRCUIT_UNIT, DEVICE_KEY_HEATING_CIRCUIT, DEVICE_KEY_XCENTER
from .entity import KermiModbusEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from kermi_modbus import KermiDevice

    from .coordinator import KermiModbusDataUpdateCoordinator
    from .data import KermiModbusConfigEntry


@dataclass(frozen=True, kw_only=True)
class KermiBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor description bound to a value getter on ``KermiDevice``."""

    device_key: str
    value_fn: Callable[[KermiDevice], bool | None]


XCENTER_BINARY_SENSORS: tuple[KermiBinarySensorEntityDescription, ...] = (
    KermiBinarySensorEntityDescription(
        key="alarm_active",
        translation_key="alarm_active",
        device_key=DEVICE_KEY_XCENTER,
        value_fn=lambda device: bool(device.xcenter.alarm.active),
    ),
)

HEATING_CIRCUIT_BINARY_SENSORS: tuple[KermiBinarySensorEntityDescription, ...] = (
    KermiBinarySensorEntityDescription(
        key="summer_mode_active",
        translation_key="summer_mode_active",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        value_fn=lambda device: bool(
            device.heating_circuit_module.heating_circuit.summer_mode_active
        ),
    ),
    KermiBinarySensorEntityDescription(
        key="cooling_mode_active",
        translation_key="cooling_mode_active",
        device_key=DEVICE_KEY_HEATING_CIRCUIT,
        value_fn=lambda device: bool(
            device.heating_circuit_module.heating_circuit.cooling_mode_active
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required by the platform signature
    entry: KermiModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up status binary sensors for one config entry."""
    coordinator = entry.runtime_data.coordinator
    descriptions = list(XCENTER_BINARY_SENSORS)
    if entry.data.get(CONF_HEATING_CIRCUIT_UNIT) is not None:
        descriptions.extend(HEATING_CIRCUIT_BINARY_SENSORS)

    async_add_entities(
        KermiModbusBinarySensor(coordinator, description) for description in descriptions
    )


class KermiModbusBinarySensor(KermiModbusEntity, BinarySensorEntity):
    """One read-only status flag."""

    entity_description: KermiBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: KermiModbusDataUpdateCoordinator,
        entity_description: KermiBinarySensorEntityDescription,
    ) -> None:
        """Bind this binary sensor to its description and a stable unique ID."""
        super().__init__(coordinator, entity_description.device_key)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.device_key}_{entity_description.key}"
        )

    @property
    def is_on(self) -> bool | None:
        """Current flag state, read live off the device object graph."""
        return self.entity_description.value_fn(self.coordinator.config_entry.runtime_data.device)
