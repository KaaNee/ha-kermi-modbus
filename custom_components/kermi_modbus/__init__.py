"""Kermi (Modbus) integration.

Uses HA's shared Modbus connection (``homeassistant.components.modbus``,
2026.9+ "Modernizing Modbus") instead of opening its own socket. Unlike
``e3dc_modbus`` (one unit, one device), a Kermi installation is up to three
Modbus units sharing one host/port (project plan §3/§10.1): the x-center
(always configured) plus the heating-circuit and/or DHW storage-module units
(each optional, independent) — modelled here as up to three HA devices,
the storage modules linked to the x-center via ``via_device_id``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.loader import async_get_loaded_integration
from modbus_connection import ModbusTcpParams

from kermi_modbus import KermiDevice
from kermi_modbus.models import XChangeDynamicProProfile

from .const import (
    CONF_DHW_UNIT,
    CONF_HEATING_CIRCUIT_UNIT,
    CONF_PV_ENABLED,
    CONF_XCENTER_UNIT,
    DEFAULT_PV_ENABLED,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DEVICE_KEY_DHW,
    DEVICE_KEY_HEATING_CIRCUIT,
    DEVICE_KEY_XCENTER,
    DOMAIN,
    LOGGER,
)
from .coordinator import KermiModbusDataUpdateCoordinator
from .data import KermiModbusData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import KermiModbusConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


def _build_device_infos(
    hass: HomeAssistant, entry: KermiModbusConfigEntry
) -> dict[str, DeviceInfo]:
    """One DeviceInfo per configured unit.

    No manufacturer/model/serial register exists to read (see
    ``kermi_modbus.models._base``), so identity comes entirely from what the
    user configured — ``model`` is the static profile name, not probed.

    ``via_device_id`` (unlike the deprecated ``via_device``) needs the
    x-center's actual device-registry id, not just its identifiers, so the
    x-center device is registered explicitly here rather than left to the
    entity platform.
    """
    xcenter_identifier = f"{entry.entry_id}_{DEVICE_KEY_XCENTER}"
    xcenter_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, xcenter_identifier)},
        manufacturer="Kermi",
        model=XChangeDynamicProProfile.name,
        name=f"Kermi {XChangeDynamicProProfile.name}",
    )
    device_infos = {
        DEVICE_KEY_XCENTER: DeviceInfo(
            identifiers={(DOMAIN, xcenter_identifier)},
            manufacturer="Kermi",
            model=XChangeDynamicProProfile.name,
            name=f"Kermi {XChangeDynamicProProfile.name}",
        ),
    }
    if entry.data.get(CONF_HEATING_CIRCUIT_UNIT) is not None:
        device_infos[DEVICE_KEY_HEATING_CIRCUIT] = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{DEVICE_KEY_HEATING_CIRCUIT}")},
            manufacturer="Kermi",
            model="Speichersystemmodul (Heizkreis)",
            name="Kermi Heizkreis",
            via_device_id=xcenter_device.id,
        )
    if entry.data.get(CONF_DHW_UNIT) is not None:
        device_infos[DEVICE_KEY_DHW] = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{DEVICE_KEY_DHW}")},
            manufacturer="Kermi",
            model="Speichersystemmodul (TWE)",
            name="Kermi Trinkwassererwärmung",
            via_device_id=xcenter_device.id,
        )
    return device_infos


async def async_setup_entry(hass: HomeAssistant, entry: KermiModbusConfigEntry) -> bool:
    """Set up Kermi (Modbus) from a config entry."""
    params = ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT])
    xcenter_unit = async_get_unit(hass, entry, params, entry.data[CONF_XCENTER_UNIT])
    heating_circuit_unit = None
    if (heating_circuit_unit_id := entry.data.get(CONF_HEATING_CIRCUIT_UNIT)) is not None:
        heating_circuit_unit = async_get_unit(hass, entry, params, heating_circuit_unit_id)
    dhw_unit = None
    if (dhw_unit_id := entry.data.get(CONF_DHW_UNIT)) is not None:
        dhw_unit = async_get_unit(hass, entry, params, dhw_unit_id)

    device = KermiDevice(
        xcenter_unit,
        heating_circuit_unit=heating_circuit_unit,
        dhw_unit=dhw_unit,
        include_pv_modulation=entry.options.get(CONF_PV_ENABLED, DEFAULT_PV_ENABLED),
    )

    coordinator = KermiModbusDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(
            seconds=entry.options.get("update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS)
        ),
        config_entry=entry,
    )
    entry.runtime_data = KermiModbusData(
        device=device,
        coordinator=coordinator,
        integration=async_get_loaded_integration(hass, entry.domain),
        device_infos=_build_device_infos(hass, entry),
    )

    # First refresh here (not deferred to the coordinator's own schedule) so
    # setup fails cleanly if the device doesn't answer, instead of entities
    # starting up in an unknown state. See:
    # https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: KermiModbusConfigEntry) -> None:
    """Reload the entry when options change (pv_enabled / update interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: KermiModbusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
