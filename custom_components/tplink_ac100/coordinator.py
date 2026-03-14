"""Data update coordinator for TP-Link TL-AC100."""
from __future__ import annotations

from datetime import timedelta
import logging
import urllib.parse
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TLAC100ApiClient, TLAC100ApiError
from .const import DOMAIN


def _normalize_mac(mac: str) -> str:
    """Convert MAC to lowercase colon format: aa:bb:cc:dd:ee:ff."""
    return mac.replace("-", ":").lower()

_LOGGER = logging.getLogger(__name__)


class TLAC100DataCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from AC100."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TLAC100ApiClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.model_map: dict[str, str] = {}
        self._model_map_fetched = False

    async def _async_update_data(self) -> dict[str, Any]:
        # Only login if no token yet; _api() handles re-auth on -40401
        if not self.client._stok:
            try:
                await self.client.async_login()
            except TLAC100ApiError as err:
                raise UpdateFailed(f"Login failed: {err}") from err

        terminals: list[dict] = []
        aps: list[dict] = []

        try:
            terminals = await self.client.async_get_terminal_list()
            _LOGGER.debug("Got %d terminals from AC100", len(terminals))
        except TLAC100ApiError as err:
            _LOGGER.error("Failed to get terminal list: %s", err)

        try:
            aps = await self.client.async_get_ap_list()
            _LOGGER.debug("Got %d APs from AC100", len(aps))
        except TLAC100ApiError as err:
            _LOGGER.error("Failed to get AP list: %s", err)

        # Fetch model list once
        if not self._model_map_fetched:
            try:
                self.model_map = await self.client.async_get_model_list()
                self._model_map_fetched = True
                _LOGGER.debug("Got %d AP models", len(self.model_map))
            except TLAC100ApiError as err:
                _LOGGER.warning("Failed to get model list: %s", err)

        if not terminals and not aps:
            raise UpdateFailed("Failed to get any data from AC100")

        # Build a dict keyed by normalized MAC for device tracker
        devices: dict[str, dict[str, Any]] = {}
        for t in terminals:
            raw_mac = t.get("mac", "")
            if not raw_mac:
                continue
            mac = _normalize_mac(raw_mac)
            is_online = bool(t.get("serv_id") and t.get("serv_id") != "-1")

            # RF info
            rf_entries = t.get("rf_entry", [])
            freq = ""
            rssi = ""
            nego_rate = ""
            if rf_entries:
                rf = rf_entries[0]
                freq = rf.get("freq_name", "")
                rssi = rf.get("rssi", "")
                nego_rate = rf.get("nego_rate", "")

            devices[mac] = {
                "mac": mac,
                "raw_mac": raw_mac,
                "hostname": urllib.parse.unquote(t.get("hostname", "")),
                "ip": t.get("ip", ""),
                "ap_name": urllib.parse.unquote(t.get("ap_name", "")),
                "ssid": urllib.parse.unquote(t.get("ssid", "")),
                "is_online": is_online,
                "blocked": t.get("blocked") == "1",
                "auth_type": t.get("auth_type", ""),
                "frequency": freq,
                "rssi": rssi,
                "nego_rate": nego_rate,
                "connect_date": urllib.parse.unquote(t.get("connect_date", "")),
                "connect_time": urllib.parse.unquote(t.get("connect_time", "")),
                "up_speed": t.get("up_speed", ""),
                "down_speed": t.get("down_speed", ""),
                "vlan_id": t.get("vlan_id", ""),
                "brand": urllib.parse.unquote(t.get("brand", "")),
            }

        # Normalize AP MACs for consistency
        normalized_aps = []
        for ap in aps:
            norm_ap = dict(ap)
            if "mac" in norm_ap:
                norm_ap["mac"] = _normalize_mac(norm_ap["mac"])
            normalized_aps.append(norm_ap)

        _LOGGER.debug(
            "Coordinator update complete: %d devices, %d APs",
            len(devices), len(normalized_aps),
        )
        if devices:
            sample_mac = next(iter(devices))
            sample = devices[sample_mac]
            _LOGGER.debug(
                "Sample device: mac=%s, ip=%s, hostname=%s, rssi=%s, ap=%s",
                sample.get("mac"), sample.get("ip"),
                sample.get("hostname"), sample.get("rssi"),
                sample.get("ap_name"),
            )

        return {
            "devices": devices,
            "aps": normalized_aps,
        }
