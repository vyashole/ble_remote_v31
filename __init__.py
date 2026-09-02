from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BleRemoteV31Coordinator

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    coordinator = BleRemoteV31Coordinator(hass)
    await coordinator.async_start()
    hass.data[DOMAIN] = coordinator
    return True

async def async_unload(hass: HomeAssistant, config_entry: ConfigEntry | None = None) -> bool:
    coordinator: BleRemoteV31Coordinator | None = hass.data.get(DOMAIN)
    if coordinator:
        await coordinator.async_stop()
        hass.data.pop(DOMAIN, None)
    return True
