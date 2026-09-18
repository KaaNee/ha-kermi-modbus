"""Constants for the Kermi (Modbus) integration."""

from __future__ import annotations

import logging

DOMAIN = "kermi_modbus"
LOGGER = logging.getLogger(__package__)

ATTRIBUTION = "Data read locally from the Kermi heat pump's Modbus/TCP interface"

# Not in homeassistant.const — Kermi's per-subsystem Modbus unit/slave IDs
# (project plan §3/§10.1): the x-center controller and the two storage-module
# domains sit on separate unit IDs behind the same host/port, not separate
# hosts.
CONF_XCENTER_UNIT = "xcenter_unit"
CONF_HEATING_CIRCUIT_UNIT = "heating_circuit_unit"
CONF_DHW_UNIT = "dhw_unit"
CONF_PV_ENABLED = "pv_enabled"

DEFAULT_PORT = 502
DEFAULT_XCENTER_UNIT = 40
DEFAULT_HEATING_CIRCUIT_UNIT = 50
DEFAULT_DHW_UNIT = 51
DEFAULT_PV_ENABLED = False

#: How often to poll the device, in seconds. Deliberately more conservative
#: than ha-e3dc-modbus's 10s default: project plan §8 documents the x-center
#: as polling-sensitive (observed `unavailable` phases in the real
#: installation's logbook history at more aggressive intervals), and this
#: integration reads up to three units per cycle instead of one. Configurable
#: per entry via the options flow — see config_flow.py.
DEFAULT_UPDATE_INTERVAL_SECONDS = 30
MIN_UPDATE_INTERVAL_SECONDS = 10

# Device-registry keys, used both for entity.py's per-subsystem DeviceInfo
# and as the device_key on entity descriptions in sensor.py/binary_sensor.py.
DEVICE_KEY_XCENTER = "xcenter"
DEVICE_KEY_HEATING_CIRCUIT = "heating_circuit"
DEVICE_KEY_DHW = "dhw"
