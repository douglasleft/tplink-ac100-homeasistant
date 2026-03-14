"""Device tracker platform for TP-Link TL-AC100."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME, DOMAIN, AUTH_TYPE_MAP
from .coordinator import TLAC100DataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker from config entry."""
    coordinator: TLAC100DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    consider_home = entry.options.get(
        CONF_CONSIDER_HOME,
        entry.data.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
    )
    host = entry.data[CONF_HOST]

    tracked: set[str] = set()

    @callback
    def _async_update_items() -> None:
        if not coordinator.data:
            _LOGGER.debug("device_tracker: coordinator.data is None/empty")
            return
        devices = coordinator.data.get("devices", {})
        _LOGGER.debug("device_tracker: %d devices in coordinator data", len(devices))
        new_entities = []
        for mac in devices:
            if mac not in tracked:
                tracked.add(mac)
                new_entities.append(
                    TLAC100DeviceTracker(coordinator, host, mac, consider_home)
                )
        if new_entities:
            _LOGGER.debug("device_tracker: adding %d new entities", len(new_entities))
            async_add_entities(new_entities)

    _async_update_items()
    entry.async_on_unload(coordinator.async_add_listener(_async_update_items))


class TLAC100DeviceTracker(CoordinatorEntity[TLAC100DataCoordinator], ScannerEntity):
    """Representation of a tracked device on AC100."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: TLAC100DataCoordinator,
        host: str,
        mac: str,
        consider_home: int,
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._mac = mac
        self._consider_home = timedelta(seconds=consider_home)
        self._last_seen: float | None = None
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}"

    @property
    def _dev_data(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.get("devices", {}).get(self._mac, {})
        return {}

    @property
    def device_info(self) -> DeviceInfo:
        """Dynamic device info - updates hostname on each refresh."""
        info = self._dev_data
        hostname = info.get("hostname") or self._mac
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=hostname,
            via_device=(DOMAIN, self._host),
            connections={("mac", self._mac)},
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        info = self._dev_data
        if info.get("is_online"):
            self._last_seen = dt_util.utcnow().timestamp()
            return True
        if self._last_seen and self._consider_home.total_seconds() > 0:
            elapsed = dt_util.utcnow().timestamp() - self._last_seen
            if elapsed < self._consider_home.total_seconds():
                return True
        return False

    @property
    def ip_address(self) -> str | None:
        return self._dev_data.get("ip") or None

    @property
    def mac_address(self) -> str | None:
        return self._mac

    @property
    def hostname(self) -> str | None:
        return self._dev_data.get("hostname") or None

    @property
    def extra_state_attributes(self) -> dict:
        info = self._dev_data
        if not info:
            return {}

        # Connection time
        connect_at = ""
        if info.get("connect_date") and info.get("connect_time"):
            connect_at = f"{info['connect_date']} {info['connect_time']}"

        return {
            "ip": info.get("ip", ""),
            "mac": info.get("mac", ""),
            "ap_name": info.get("ap_name", ""),
            "ssid": info.get("ssid", ""),
            "frequency": info.get("frequency", ""),
            "rssi": info.get("rssi", ""),
            "nego_rate": info.get("nego_rate", ""),
            "connected_at": connect_at,
            "up_speed": info.get("up_speed", ""),
            "down_speed": info.get("down_speed", ""),
            "vlan_id": info.get("vlan_id", ""),
            "brand": info.get("brand", ""),
            "auth_type": AUTH_TYPE_MAP.get(
                info.get("auth_type", ""), info.get("auth_type", "")
            ),
            "blocked": info.get("blocked", False),
        }
