from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, EVENT_BLE_REMOTE_BUTTON_PRESSED

_LOGGER = logging.getLogger(__name__)

REMOTE_MAC = "10:9E:3A:10:25:5D"
REMOTE_SERVICE_UUID = "000008f0-0000-1000-8000-00805f9b34fb"

def parse_remote_command(service_data: bytes) -> dict[str, Any] | None:
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
        _LOGGER.info("BleRemoteV31Coordinator async_start called")

        @callback
        def _async_discovered_device(service_info: BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange) -> None:
            _LOGGER.info("BLE callback invoked for %s (change=%s)", service_info.address, change)

            if service_info.address.upper() != REMOTE_MAC.upper():
                _LOGGER.debug("MAC mismatch: %s != %s", service_info.address.upper(), REMOTE_MAC.upper())
                return

            _LOGGER.debug(
                "BLE adv from %s: service_data=%s",
                service_info.address,
                {str(k): v.hex() for k, v in service_info.service_data.items()},
            )

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
                _LOGGER.debug("parse_remote_command returned None for %s", service_data.hex())
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

        # Official pattern from the docs: single dict matcher + scanning mode [107]
        self._cancel_listen = bluetooth.async_register_callback(
            self.hass,
            _async_discovered_device,
            {
                "service_uuid": REMOTE_SERVICE_UUID,
                "connectable": False,
            },
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

    async def async_stop(self) -> None:
        if self._cancel_listen:
            self._cancel_listen()
            self._cancel_listen = None
