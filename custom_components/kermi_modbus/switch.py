"""Switch platform for Kermi (Modbus): the one writable boolean register.

Covers the last of the 15 documented writable registers (project plan §9
Phase 2): DHW single-charge (address 103, "Einmalladung") — a plain 0/1
register, corrected in this project from the real production YAML's
copy-paste bug (see kermi-modbus's const.py). Likely a momentary
"trigger a one-off charge" flag rather than a persisted mode — this
switch just reflects whatever the device reports, on or off.

After a write, this re-reads just the affected component directly
(``component.async_update()``) rather than calling
``coordinator.async_request_refresh()`` — confirmed (2026-09-14, test suite)
that ``DataUpdateCoordinator.async_request_refresh()`` debounces with a
10-second cooldown (``REQUEST_REFRESH_DEFAULT_COOLDOWN``), so two writes
within 10s of each other would leave the entity showing the *first*
write's state until the coordinator's next natural poll. A direct re-read
is also cheaper than a full-device refresh through the coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .const import CONF_DHW_UNIT, DEVICE_KEY_DHW
from .entity import KermiModbusEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from kermi_modbus import KermiDevice

    from .coordinator import KermiModbusDataUpdateCoordinator
    from .data import KermiModbusConfigEntry


@dataclass(frozen=True, kw_only=True)
class KermiSwitchEntityDescription(SwitchEntityDescription):
    """Switch description bound to one writable boolean field on a Kermi component."""

    device_key: str
    component_fn: Callable[[KermiDevice], Any]
    field: str


DHW_SWITCHES: tuple[KermiSwitchEntityDescription, ...] = (
    KermiSwitchEntityDescription(
        key="dhw_single_charge",
        translation_key="dhw_single_charge",
        device_key=DEVICE_KEY_DHW,
        component_fn=lambda device: device.dhw_module.dhw,
        field="single_charge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required by the platform signature
    entry: KermiModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable boolean switches for one config entry."""
    coordinator = entry.runtime_data.coordinator
    descriptions: list[KermiSwitchEntityDescription] = []
    if entry.data.get(CONF_DHW_UNIT) is not None:
        descriptions.extend(DHW_SWITCHES)

    async_add_entities(KermiModbusSwitch(coordinator, description) for description in descriptions)


class KermiModbusSwitch(KermiModbusEntity, SwitchEntity):
    """A single writable Kermi boolean register."""

    entity_description: KermiSwitchEntityDescription

    def __init__(
        self,
        coordinator: KermiModbusDataUpdateCoordinator,
        entity_description: KermiSwitchEntityDescription,
    ) -> None:
        """Bind this switch to its description and a stable unique ID."""
        super().__init__(coordinator, entity_description.device_key)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.device_key}_{entity_description.key}"
        )

    @property
    def is_on(self) -> bool | None:
        """Current flag state, read live off the device object graph."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        value = getattr(component, self.entity_description.field)
        return bool(value) if value is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:  # noqa: ARG002
        """Set this flag, then read it straight back and push the new state."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        await component.write(self.entity_description.field, 1)
        await component.async_update()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:  # noqa: ARG002
        """Clear this flag, then read it straight back and push the new state."""
        component = self.entity_description.component_fn(
            self.coordinator.config_entry.runtime_data.device
        )
        await component.write(self.entity_description.field, 0)
        await component.async_update()
        self.async_write_ha_state()
