"""Runtime data for the Kermi (Modbus) integration.

Stored on ``ConfigEntry.runtime_data`` per current HA convention — not in
``hass.data[DOMAIN]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.loader import Integration

    from kermi_modbus import KermiDevice

    from .coordinator import KermiModbusDataUpdateCoordinator

type KermiModbusConfigEntry = ConfigEntry[KermiModbusData]


@dataclass
class KermiModbusData:
    """Everything a platform needs, reachable via ``entry.runtime_data``."""

    device: KermiDevice
    coordinator: KermiModbusDataUpdateCoordinator
    integration: Integration
    #: One DeviceInfo per configured subsystem (const.DEVICE_KEY_*) — always
    #: has DEVICE_KEY_XCENTER; DEVICE_KEY_HEATING_CIRCUIT/DEVICE_KEY_DHW are
    #: present only if that unit was configured. See entity.py.
    device_infos: dict[str, DeviceInfo]
