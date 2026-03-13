"""Sensor platform for TP-Link TL-AC100."""
from __future__ import annotations

import logging
import urllib.parse

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TLAC100DataCoordinator

_LOGGER = logging.getLogger(__name__)


def _fmt_duration(seconds) -> str:
    s = int(seconds) if seconds else 0
    if s <= 0:
        return "offline"
    h, m = s // 3600, (s % 3600) // 60
    if h > 24:
        d = h // 24
        h = h % 24
        return f"{d}d {h}h {m}m"
    return f"{h}h {m}m"


def _ac100_device_info(host: str) -> DeviceInfo:
    """Device info for the AC100 controller."""
    return DeviceInfo(
        identifiers={(DOMAIN, host)},
        name="TP-Link AC100",
        manufacturer="TP-Link",
        model="TL-AC100",
    )


def _ap_device_info(host: str, mac: str, name: str) -> DeviceInfo:
    """Device info for an AP managed by AC100."""
    return DeviceInfo(
        identifiers={(DOMAIN, mac)},
        name=name,
        manufacturer="TP-Link",
        via_device=(DOMAIN, host),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from config entry."""
    coordinator: TLAC100DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]

    tracked: set[str] = set()

    @callback
    def _async_update_items() -> None:
        if not coordinator.data:
            return
        aps = coordinator.data.get("aps", [])
        new_entities: list[SensorEntity] = []

        # --- AC100 controller sensors (created once) ---
        if "__ac100_clients" not in tracked:
            tracked.add("__ac100_clients")
            new_entities.append(AC100OnlineClientsSensor(coordinator, host))
        if "__ac100_aps" not in tracked:
            tracked.add("__ac100_aps")
            new_entities.append(AC100OnlineAPsSensor(coordinator, host))

        # --- Per-AP sensors ---
        for ap in aps:
            mac = ap.get("mac", "")
            if not mac or mac in tracked:
                continue
            tracked.add(mac)
            ap_name = urllib.parse.unquote(ap.get("entry_name", mac))
            new_entities.append(APStatusSensor(coordinator, host, mac, ap_name))
            new_entities.append(APClientsSensor(coordinator, host, mac, ap_name))
            new_entities.append(APUptimeSensor(coordinator, host, mac, ap_name))

        if new_entities:
            async_add_entities(new_entities)

    _async_update_items()
    entry.async_on_unload(coordinator.async_add_listener(_async_update_items))


# =====================================================================
#  AC100 Controller sensors
# =====================================================================

class AC100OnlineClientsSensor(CoordinatorEntity[TLAC100DataCoordinator], SensorEntity):
    """Total online clients on AC100."""

    _attr_has_entity_name = True
    _attr_name = "Online Clients"
    _attr_icon = "mdi:devices"
    _attr_native_unit_of_measurement = "clients"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TLAC100DataCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ac100_{host}_online_clients"
        self._attr_device_info = _ac100_device_info(host)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        devices = self.coordinator.data.get("devices", {})
        return sum(1 for d in devices.values() if d.get("is_online"))


class AC100OnlineAPsSensor(CoordinatorEntity[TLAC100DataCoordinator], SensorEntity):
    """Total online APs on AC100."""

    _attr_has_entity_name = True
    _attr_name = "Online APs"
    _attr_icon = "mdi:access-point-network"
    _attr_native_unit_of_measurement = "APs"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TLAC100DataCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"ac100_{host}_online_aps"
        self._attr_device_info = _ac100_device_info(host)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        aps = self.coordinator.data.get("aps", [])
        return sum(1 for a in aps if a.get("link_status") == "1")


# =====================================================================
#  Per-AP sensors
# =====================================================================

class _APSensorBase(CoordinatorEntity[TLAC100DataCoordinator], SensorEntity):
    """Base class for per-AP sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: TLAC100DataCoordinator, host: str, mac: str, ap_name: str
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_device_info = _ap_device_info(host, mac, ap_name)

    @property
    def _ap_info(self) -> dict:
        if not self.coordinator.data:
            return {}
        for ap in self.coordinator.data.get("aps", []):
            if ap.get("mac") == self._mac:
                return ap
        return {}


class APStatusSensor(_APSensorBase):
    """AP online/offline status."""

    _attr_name = "Status"
    _attr_icon = "mdi:access-point"

    def __init__(self, coordinator, host, mac, ap_name):
        super().__init__(coordinator, host, mac, ap_name)
        self._attr_unique_id = f"ac100_ap_{mac}_status"

    @property
    def native_value(self) -> str:
        info = self._ap_info
        if not info:
            return "unknown"
        return "online" if info.get("link_status") == "1" else "offline"

    @property
    def extra_state_attributes(self) -> dict:
        info = self._ap_info
        if not info:
            return {}
        attrs = {
            "mac": info.get("mac", ""),
            "ip": info.get("ip", ""),
        }
        rf_entries = info.get("rf_entry", [])
        for rf in rf_entries:
            freq = rf.get("freq_name", "")
            attrs[f"{freq}_channel"] = rf.get("channel", "")
            attrs[f"{freq}_load"] = urllib.parse.unquote(rf.get("channel_load", ""))
        return attrs


class APClientsSensor(_APSensorBase):
    """Number of clients connected to this AP."""

    _attr_name = "Clients"
    _attr_icon = "mdi:account-multiple"
    _attr_native_unit_of_measurement = "clients"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, host, mac, ap_name):
        super().__init__(coordinator, host, mac, ap_name)
        self._attr_unique_id = f"ac100_ap_{mac}_clients"

    @property
    def native_value(self) -> int:
        info = self._ap_info
        if not info:
            return 0
        total = 0
        for rf in info.get("rf_entry", []):
            total += int(rf.get("rf_client_num", 0))
        return total


class APUptimeSensor(_APSensorBase):
    """AP uptime."""

    _attr_name = "Uptime"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, host, mac, ap_name):
        super().__init__(coordinator, host, mac, ap_name)
        self._attr_unique_id = f"ac100_ap_{mac}_uptime"

    @property
    def native_value(self) -> str:
        info = self._ap_info
        if not info:
            return "unknown"
        return _fmt_duration(info.get("online_time", 0))
