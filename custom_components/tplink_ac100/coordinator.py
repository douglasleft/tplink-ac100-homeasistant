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
        self.ap_list: list[dict[str, Any]] = []
        self.terminal_list: list[dict[str, Any]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        # Force fresh login each cycle to avoid stale token issues
        # (AC100 only supports one active session)
        try:
            await self.client.async_login()
        except TLAC100ApiError as err:
            raise UpdateFailed(f"Login failed: {err}") from err

        terminals = []
        aps = []

        try:
            terminals = await self.client.async_get_terminal_list()
            _LOGGER.debug("Got %d terminals from AC100", len(terminals))
        except TLAC100ApiError as err:
            _LOGGER.error("Failed to get terminal list: %s", err)

        try:
            aps = await self.client.async_get_ap_list()
            _LOGGER.debug("Got %d APs from AC100, data: %s", len(aps), aps[:1] if aps else "empty")
        except TLAC100ApiError as err:
            _LOGGER.error("Failed to get AP list: %s", err)

        if not terminals and not aps:
            raise UpdateFailed("Failed to get any data from AC100")

        self.ap_list = aps
        self.terminal_list = terminals

        # Build a dict keyed by MAC for device tracker
        devices: dict[str, dict[str, Any]] = {}
        for t in terminals:
            mac = t.get("mac", "")
            if not mac:
                continue
            is_online = bool(t.get("serv_id") and t.get("serv_id") != "-1")

            # RF info
            rf_entries = t.get("rf_entry", [])
            freq = ""
            signal = ""
            rx_rate = ""
            tx_rate = ""
            if rf_entries:
                rf = rf_entries[0]
                freq = rf.get("freq_name", "")
                signal = rf.get("signal", rf.get("rssi", ""))
                rx_rate = rf.get("rx_rate", "")
                tx_rate = rf.get("tx_rate", "")

            devices[mac] = {
                "mac": mac,
                "hostname": urllib.parse.unquote(t.get("hostname", "")),
                "ip": t.get("ip", ""),
                "ap_name": urllib.parse.unquote(t.get("ap_name", "")),
                "ssid": urllib.parse.unquote(t.get("ssid", "")),
                "is_online": is_online,
                "blocked": t.get("blocked") == "1",
                "auth_type": t.get("auth_type", ""),
                "online_time": t.get("online_time", 0),
                "frequency": freq,
                "signal": signal,
                "rx_rate": rx_rate,
                "tx_rate": tx_rate,
                "rf_entry": rf_entries,
                # keep raw data for anything we might have missed
                "_raw": t,
            }

        return {
            "devices": devices,
            "aps": aps,
        }
