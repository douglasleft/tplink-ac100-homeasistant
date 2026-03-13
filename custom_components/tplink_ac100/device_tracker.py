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
    consider_home = entry.data.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
    host = entry.data[CONF_HOST]

    tracked: set[str] = set()

    @callback
    def _async_update_items() -> None:
        """Add new device trackers."""
        if not coordinator.data:
            return
        devices = coordinator.data.get("devices", {})
        new_entities = []
        for mac, info in devices.items():
            if mac not in tracked:
                tracked.add(mac)
                new_entities.append(
                    TLAC100DeviceTracker(coordinator, host, mac, consider_home)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_update_items()
    entry.async_on_unload(coordinator.async_add_listener(_async_update_items))


class TLAC100DeviceTracker(CoordinatorEntity[TLAC100DataCoordinator], ScannerEntity):
    """Representation of a tracked device on AC100."""

    _attr_has_entity_name = True

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

        info = self._dev_data
        hostname = info.get("hostname") or mac
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}"
        self._attr_name = hostname

        # Each WiFi client is its own device, linked via AC100
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=hostname,
            via_device=(DOMAIN, host),
            connections={("mac", mac)},
        )

    @property
    def _dev_data(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.get("devices", {}).get(self._mac, {})
        return {}

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        info = self._dev_data
        if info.get("is_online"):
            self._last_seen = dt_util.utcnow().timestamp()
            return True
        # Consider home grace period
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
        attrs = {}

        attrs["ip"] = info.get("ip", "")
        attrs["mac"] = info.get("mac", "")
        attrs["ap_name"] = info.get("ap_name", "")
        attrs["ssid"] = info.get("ssid", "")
        attrs["frequency"] = info.get("frequency", "")

        # Connection duration
        online_time = info.get("online_time", 0)
        attrs["online_time"] = self._fmt_duration(online_time)

        # Signal & rate
        if info.get("signal"):
            attrs["signal"] = info["signal"]
        if info.get("rx_rate"):
            attrs["rx_rate"] = info["rx_rate"]
        if info.get("tx_rate"):
            attrs["tx_rate"] = info["tx_rate"]

        attrs["auth_type"] = AUTH_TYPE_MAP.get(
            info.get("auth_type", ""), info.get("auth_type", "")
        )
        attrs["blocked"] = info.get("blocked", False)

        return attrs

    @staticmethod
    def _fmt_duration(seconds) -> str:
        s = int(seconds) if seconds else 0
        if s <= 0:
            return ""
        h, m = s // 3600, (s % 3600) // 60
        if h > 24:
            d = h // 24
            h = h % 24
            return f"{d}d {h}h {m}m"
        return f"{h}h {m}m"
