"""Button platform for TP-Link TL-AC100 (disconnect clients)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TLAC100DataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from config entry."""
    coordinator: TLAC100DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]

    tracked: set[str] = set()

    @callback
    def _async_update_items() -> None:
        if not coordinator.data:
            return
        devices = coordinator.data.get("devices", {})
        new_entities = []
        for mac in devices:
            if mac not in tracked:
                tracked.add(mac)
                new_entities.append(
                    ClientDisconnectButton(coordinator, host, mac)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_update_items()
    entry.async_on_unload(coordinator.async_add_listener(_async_update_items))


class ClientDisconnectButton(CoordinatorEntity[TLAC100DataCoordinator], ButtonEntity):
    """Button to disconnect a WiFi client."""

    _attr_has_entity_name = True
    _attr_name = "Disconnect"
    _attr_icon = "mdi:wifi-off"
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: TLAC100DataCoordinator,
        host: str,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._mac = mac
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_disconnect"

    @property
    def _dev_data(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.get("devices", {}).get(self._mac, {})
        return {}

    @property
    def device_info(self) -> DeviceInfo:
        info = self._dev_data
        hostname = info.get("hostname") or self._mac
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=hostname,
            via_device=(DOMAIN, self._host),
            connections={("mac", self._mac)},
        )

    async def async_press(self) -> None:
        """Disconnect the client."""
        info = self._dev_data
        raw_mac = info.get("raw_mac", self._mac)
        _LOGGER.info("Disconnecting client %s", raw_mac)
        await self.coordinator.client.async_disconnect_terminals([raw_mac])
        await self.coordinator.async_request_refresh()
