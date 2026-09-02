from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, BluetoothChange, async_register_callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, EVENT_BLE_REMOTE_BUTTON_PRESSED

_LOGGER = logging.getLogger(__name__)

# Your remote's MAC (from the log you just posted)
REMOTE_MAC = "10:9E:3A:10:25:5D"

# Service UUID from the advertisement
REMOTE_SERVICE_UUID = "000008f0-0000-1000-8000-00805f9b34fb"

MATCHERS = [
    {
        "service_uuids": [REMOTE_SERVICE_UUID],
    },
]

def parse_remote_command(service_data: bytes) -> dict[str, Any] | None:
    """
    Parse the service data payload for the V31 remote.

    From your log, service_data is:
      10 00 C5 85 41 A4 BB 43 1B 85 1D 90 94 06 64 6D A1 F9 66 31 86 1F FA C9

    Based on earlier analysis:
      - cmd byte at offset 0 (0x10 / 0x11)
      - index byte at offset 9 (0x06 in your example)
    """
    if len(service_data) < 10:
        _LOGGER.debug("parse_remote_command: payload too short (%d)", len(service_data))
        return None

    cmd = service_data[0]
    index = service_data[9]

    cmd_map = {
        0x10: "toggle",
        0x11: "alt_toggle",
    }

    cmd_name = cmd_map.get(cmd, f"cmd_0x{cmd:02x}")

    _LOGGER.debug("parse_remote_command: cmd=0x%02x, index=%d", cmd, index)

    return {
        "cmd_raw": cmd,
        "cmd": cmd_name,
        "index": index,
    }

class BleRemoteV31Coordinator(DataUpdateCoordinator[None]):
    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self._cancel_listen = None

    async def async_start(self) -> None:
        def _handle_advertisement(service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
            # Extra safety: filter by MAC
            if service_info.address.upper() != REMOTE_MAC.upper():
                return

            _LOGGER.debug(
                "BLE adv from %s: service_data=%s",
                service_info.address,
                {str(k): v.hex() for k, v in service_info.service_data.items()},
            )

            # Find service data for our UUID
            service_data = None
            for uuid, data in service_info.service_data.items():
                if str(uuid).lower().endswith("08f0"):
                    service_data = data
                    break

            if service_data is None:
                _LOGGER.debug("No service_data for UUID 0x08F0 from %s", service_info.address)
                return

            parsed = parse_remote_command(service_data)
            if not parsed:
                return

            _LOGGER.info(
                "Remote button pressed: index=%d, cmd=%s (raw=0x%02x)",
                parsed["index"],
                parsed["cmd"],
                parsed["cmd_raw"],
            )

            self.hass.bus.async_fire(
                EVENT_BLE_REMOTE_BUTTON_PRESSED,
                {
                    "address": service_info.address,
                    "rssi": service_info.rssi,
                    "button_index": parsed["index"],
                    "cmd": parsed["cmd"],
                    "cmd_raw": parsed["cmd_raw"],
                },
            )

        # Match advertisements that contain our service UUID
        self._cancel_listen = async_register_callback(
            self.hass,
            _handle_advertisement,
            MATCHERS,
            BluetoothChange.ADVERTISEMENT,
        )

    async def async_stop(self) -> None:
        if self._cancel_listen:
            self._cancel_listen()
            self._cancel_listen = None
