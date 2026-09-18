"""DataUpdateCoordinator for the Kermi (Modbus) integration.

The coordinator's own ``data`` stays ``None`` on purpose: ``KermiDevice`` and
its sub-blocks (``device.xcenter``, ``device.heating_circuit_module``, ...)
already hold live, mutable state after ``async_update()`` — entities read
straight off those objects (``entry.runtime_data.device.xcenter.power.cop``)
rather than off a coordinator-returned dict. The coordinator's job here is
purely scheduling + error handling for one pooled Modbus read (across up to
three units) per interval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection.exceptions import ModbusError

if TYPE_CHECKING:
    from .data import KermiModbusConfigEntry


class KermiModbusDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Poll the Kermi device once per interval."""

    config_entry: KermiModbusConfigEntry

    async def _async_update_data(self) -> None:
        """Refresh every configured unit via one pooled Modbus read.

        Raises ``UpdateFailed`` so entities go ``unavailable`` instead of
        showing a stale or crashing value on a dropped connection.
        """
        try:
            await self.config_entry.runtime_data.device.async_update()
        except ModbusError as exception:
            raise UpdateFailed(str(exception)) from exception
