from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.bluetooth import BluetoothChange

from .const import DOMAIN, EVENT_BLE_REMOTE_BUTTON_PRESSED, REMOTE_SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

# Optional: filter by MAC if you want only one remote
# REMOTE_MAC = "AA:BB:CC:DD:EE:FF"

def parse_remote_command(service_data: bytes) -> dict[str, Any] | None:
    """
    Parse the service data payload for the V31 remote.

    Based on your logs, the payload includes:
      - cmd byte (0x10 / 0x11)
      - index byte (1..4)
    The exact layout may be:
      [prefix...][cmd][param][args...][id...][index][tx][seed...]

    From your examples:
      "cmd: 0x10, param: 0x00, args: [0,0,0]"
      "id: 0x060BDDFE, index: 1, tx: 172, seed: 0xEB7B"

    We'll assume:
      - cmd at offset 4
      - index at offset 13 (adjust after inspecting a few payloads)
    """
    if len(service_data) < 14:
        return None

    # These offsets are inferred from your text; you may need to tweak them.
    cmd = service_data[4]
    index = service_data[13]

    # Map cmd values to something human‑readable
    cmd_map = {
        0x10: "toggle",
        0x11: "alt_toggle",
    }

    cmd_name = cmd_map.get(cmd, f"cmd_0x{cmd:02x}")

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
            update_interval=None,  # push‑based, no polling
        )
        self._cancel_listen = None

    async def async_start(self) -> None:
        from homeassistant.components.bluetooth import async_register_callback, BluetoothChange

        def _handle_advertisement(service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
            # Optional MAC filter:
            # if service_info.address.upper() != REMOTE_MAC.upper():
            #     return

            # We only care about service_data for our UUID
            service_data = None
            for uuid, data in service_info.service_data.items():
                # uuid can be int or UUID; normalize to string if needed
                if str(uuid).lower().endswith("08f0"):
                    service_data = data
                    break

            if service_data is None:
                return

            parsed = parse_remote_command(service_data)
            if not parsed:
                return

            # Fire custom event
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

        self._cancel_listen = async_register_callback(
            self.hass,
            _handle_advertisement,
            {
                "service_uuid": REMOTE_SERVICE_UUID,
            },
            BluetoothChange.ADVERTISEMENT,
        )

    async def async_stop(self) -> None:
        if self._cancel_listen:
            self._cancel_listen()
            self._cancel_listen = None
