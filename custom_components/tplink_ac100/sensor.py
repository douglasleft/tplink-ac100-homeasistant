"""Sensor platform for TP-Link TL-AC100."""
from __future__ import annotations

import logging
import urllib.parse

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
try:
    from homeassistant.const import EntityCategory
except ImportError:
    from homeassistant.helpers.entity import EntityCategory
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
    return DeviceInfo(
        identifiers={(DOMAIN, host)},
        name="TP-Link AC100",
        manufacturer="TP-Link",
        model="TL-AC100",
    )


def _ap_device_info(host: str, mac: str, name: str, model: str = "") -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, mac)},
        name=name,
        manufacturer="TP-Link",
        model=model or None,
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

    tracked_aps: set[str] = set()
    tracked_clients: set[str] = set()

    @callback
    def _async_update_items() -> None:
        if not coordinator.data:
            return
        new_entities: list[SensorEntity] = []

        # --- AC100 controller sensors (created once) ---
        if "__ac100_clients" not in tracked_aps:
            tracked_aps.add("__ac100_clients")
            new_entities.append(AC100OnlineClientsSensor(coordinator, host))
        if "__ac100_aps" not in tracked_aps:
            tracked_aps.add("__ac100_aps")
            new_entities.append(AC100OnlineAPsSensor(coordinator, host))

        # --- Per-AP sensors ---
        aps = coordinator.data.get("aps", [])
        for ap in aps:
            mac = ap.get("mac", "")
            if not mac or mac in tracked_aps:
                continue
            tracked_aps.add(mac)
            ap_name = urllib.parse.unquote(ap.get("entry_name", mac))
            model_id = ap.get("model_id", "")
            model_name = coordinator.model_map.get(model_id, "")
            new_entities.append(APClientsSensor(coordinator, host, mac, ap_name, model_name))
            new_entities.append(APUptimeSensor(coordinator, host, mac, ap_name, model_name))

        # --- Per-client sensors ---
        devices = coordinator.data.get("devices", {})
        for mac, info in devices.items():
            if mac not in tracked_clients:
                tracked_clients.add(mac)
                new_entities.append(ClientSignalSensor(coordinator, host, mac))
                new_entities.append(ClientIPSensor(coordinator, host, mac))
                new_entities.append(ClientAPSensor(coordinator, host, mac))
                new_entities.append(ClientSSIDSensor(coordinator, host, mac))
                new_entities.append(ClientConnectedAtSensor(coordinator, host, mac))

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
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: TLAC100DataCoordinator,
        host: str, mac: str, ap_name: str, model_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._mac = mac
        self._ap_name_fallback = ap_name
        self._model_name = model_name

    @property
    def _ap_info(self) -> dict:
        if not self.coordinator.data:
            return {}
        for ap in self.coordinator.data.get("aps", []):
            if ap.get("mac") == self._mac:
                return ap
        return {}

    @property
    def device_info(self) -> DeviceInfo:
        info = self._ap_info
        entry_name = info.get("entry_name") if info else None
        ap_name = urllib.parse.unquote(entry_name) if entry_name else self._ap_name_fallback
        return _ap_device_info(self._host, self._mac, ap_name, self._model_name)


class APClientsSensor(_APSensorBase):
    """Number of clients connected to this AP."""

    _attr_name = "Clients"
    _attr_icon = "mdi:account-multiple"
    _attr_native_unit_of_measurement = "clients"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, host, mac, ap_name, model_name):
        super().__init__(coordinator, host, mac, ap_name, model_name)
        self._attr_unique_id = f"ac100_ap_{mac.replace(':', '_')}_clients"

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
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac, ap_name, model_name):
        super().__init__(coordinator, host, mac, ap_name, model_name)
        self._attr_unique_id = f"ac100_ap_{mac.replace(':', '_')}_uptime"

    @property
    def native_value(self) -> str:
        info = self._ap_info
        if not info:
            return "unknown"
        return _fmt_duration(info.get("online_time", 0))


# =====================================================================
#  Per-client signal sensor
# =====================================================================

class _ClientSensorBase(CoordinatorEntity[TLAC100DataCoordinator], SensorEntity):
    """Base class for per-client sensors."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: TLAC100DataCoordinator, host: str, mac: str
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._mac = mac

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


class ClientSignalSensor(_ClientSensorBase):
    """WiFi signal strength of a client."""

    _attr_name = "Signal"
    _attr_icon = "mdi:wifi"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac):
        super().__init__(coordinator, host, mac)
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_signal"

    @property
    def native_value(self) -> int | None:
        rssi = self._dev_data.get("rssi", "")
        if not rssi or not self._dev_data.get("is_online"):
            return None
        try:
            return int(rssi)
        except (ValueError, TypeError):
            return None


class ClientIPSensor(_ClientSensorBase):
    """IP address of a client."""

    _attr_name = "IP Address"
    _attr_icon = "mdi:ip-network"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac):
        super().__init__(coordinator, host, mac)
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_ip"

    @property
    def native_value(self) -> str | None:
        return self._dev_data.get("ip") or None


class ClientAPSensor(_ClientSensorBase):
    """Connected AP name of a client."""

    _attr_name = "Connected AP"
    _attr_icon = "mdi:access-point"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac):
        super().__init__(coordinator, host, mac)
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_ap"

    @property
    def native_value(self) -> str | None:
        return self._dev_data.get("ap_name") or None


class ClientSSIDSensor(_ClientSensorBase):
    """Connected SSID of a client."""

    _attr_name = "SSID"
    _attr_icon = "mdi:wifi-settings"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac):
        super().__init__(coordinator, host, mac)
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_ssid"

    @property
    def native_value(self) -> str | None:
        return self._dev_data.get("ssid") or None


class ClientConnectedAtSensor(_ClientSensorBase):
    """Connection time of a client."""

    _attr_name = "Connected At"
    _attr_icon = "mdi:clock-start"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, host, mac):
        super().__init__(coordinator, host, mac)
        self._attr_unique_id = f"ac100_{mac.replace(':', '_')}_connected_at"

    @property
    def native_value(self) -> str | None:
        info = self._dev_data
        d = info.get("connect_date", "")
        t = info.get("connect_time", "")
        if d and t:
            return f"{d} {t}"
        return None
