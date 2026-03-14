"""Binary sensor platform for TP-Link TL-AC100 (AP online/offline)."""
from __future__ import annotations

import logging
import urllib.parse

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up binary sensor entities from config entry."""
    coordinator: TLAC100DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]

    tracked: set[str] = set()

    @callback
    def _async_update_items() -> None:
        if not coordinator.data:
            return
        aps = coordinator.data.get("aps", [])
        new_entities = []
        for ap in aps:
            mac = ap.get("mac", "")
            if not mac or mac in tracked:
                continue
            tracked.add(mac)
            ap_name = urllib.parse.unquote(ap.get("entry_name", mac))
            model_id = ap.get("model_id", "")
            model_name = coordinator.model_map.get(model_id, "")
            new_entities.append(
                APStatusBinarySensor(coordinator, host, mac, ap_name, model_name)
            )
        if new_entities:
            async_add_entities(new_entities)

    _async_update_items()
    entry.async_on_unload(coordinator.async_add_listener(_async_update_items))


class APStatusBinarySensor(
    CoordinatorEntity[TLAC100DataCoordinator], BinarySensorEntity
):
    """Binary sensor for AP online/offline status."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: TLAC100DataCoordinator,
        host: str,
        mac: str,
        ap_name: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"ac100_ap_{mac.replace(':', '_')}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=ap_name,
            manufacturer="TP-Link",
            model=model_name or None,
            via_device=(DOMAIN, host),
        )

    @property
    def _ap_info(self) -> dict:
        if not self.coordinator.data:
            return {}
        for ap in self.coordinator.data.get("aps", []):
            if ap.get("mac") == self._mac:
                return ap
        return {}

    @property
    def is_on(self) -> bool | None:
        info = self._ap_info
        if not info:
            return None
        return info.get("link_status") == "1"

    @property
    def extra_state_attributes(self) -> dict:
        info = self._ap_info
        if not info:
            return {}
        attrs = {
            "mac": info.get("mac", ""),
            "ip": info.get("ip", ""),
        }
        for rf in info.get("rf_entry", []):
            freq = rf.get("freq_name", "")
            attrs[f"{freq}_channel"] = rf.get("channel", "")
            attrs[f"{freq}_load"] = urllib.parse.unquote(rf.get("channel_load", ""))
        return attrs
