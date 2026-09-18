"""Base entity for the Kermi (Modbus) integration.

Unlike ``e3dc_modbus`` (one device per config entry), a Kermi installation is
1-3 devices sharing one config entry: the x-center always, plus whichever of
the heating-circuit/DHW storage modules were configured (project plan §10.1
— these are confirmed functionally separate physical modules, not one device
answering twice). Every entity picks its device via ``device_key``
(``const.DEVICE_KEY_*``); the heating-circuit/DHW devices are linked to the
x-center via ``via_device``, see ``__init__.py`` where the DeviceInfo objects
are built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION
from .coordinator import KermiModbusDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceInfo


class KermiModbusEntity(CoordinatorEntity[KermiModbusDataUpdateCoordinator]):
    """Common device_info/attribution/naming for every kermi_modbus entity."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: KermiModbusDataUpdateCoordinator, device_key: str) -> None:
        """Tie this entity to one of the 1-3 devices this config entry represents."""
        super().__init__(coordinator)
        self._device_key = device_key
        device_infos = coordinator.config_entry.runtime_data.device_infos
        self._attr_device_info: DeviceInfo = device_infos[device_key]
