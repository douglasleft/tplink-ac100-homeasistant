"""TP-Link TL-AC100 API Client (new firmware with nonce auth)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import urllib.parse
from typing import Any

import aiohttp

from .const import API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class TLAC100ApiError(Exception):
    """Base exception for API errors."""


class TLAC100AuthError(TLAC100ApiError):
    """Authentication failed."""


class TLAC100ConnectionError(TLAC100ApiError):
    """Connection failed."""


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _decode_val(val: Any) -> Any:
    if isinstance(val, str):
        return urllib.parse.unquote(val)
    return val


def _parse_list(data: list) -> list[dict]:
    """Parse TP-LINK nested list format [{key_N: {...}}, ...] -> [dict, ...]."""
    result = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for val in item.values():
                    result.append(val)
    return result


class TLAC100ApiClient:
    """Async API client for TP-Link TL-AC100."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._stok: str | None = None
        self._base_url = f"http://{host}"

    @property
    def host(self) -> str:
        return self._host

    async def _post(self, url: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        async with asyncio.timeout(API_TIMEOUT):
            async with self._session.post(
                url, json=payload, headers=headers
            ) as resp:
                return await resp.json(content_type=None)

    async def async_login(self) -> bool:
        """Login with nonce-based MD5 auth (new firmware)."""
        # Step 1: get encrypt info (nonce)
        try:
            data = await self._post(
                f"{self._base_url}/",
                {"method": "do", "user_management": {"get_encrypt_info": None}},
            )
        except asyncio.TimeoutError as err:
            raise TLAC100ConnectionError("Connection timeout") from err
        except aiohttp.ClientError as err:
            raise TLAC100ConnectionError(f"Connection error: {err}") from err

        if data.get("error_code") != 0:
            raise TLAC100AuthError(
                f"Failed to get encrypt info: error_code={data.get('error_code')}"
            )

        nonce = data.get("nonce")
        if not nonce:
            raise TLAC100AuthError("No nonce in encrypt info response")

        # Step 2: login with md5(password:nonce)
        encrypted_pwd = _md5(f"{self._password}:{nonce}")
        try:
            data = await self._post(
                f"{self._base_url}/",
                {
                    "method": "do",
                    "login": {
                        "username": self._username,
                        "password": encrypted_pwd,
                        "encrypt_type": "3",
                    },
                },
            )
        except asyncio.TimeoutError as err:
            raise TLAC100ConnectionError("Connection timeout") from err
        except aiohttp.ClientError as err:
            raise TLAC100ConnectionError(f"Connection error: {err}") from err

        if data.get("error_code") != 0:
            raise TLAC100AuthError(
                f"Login failed: error_code={data.get('error_code')}"
            )

        self._stok = data.get("stok")
        if not self._stok:
            raise TLAC100AuthError("No stok in login response")

        _LOGGER.debug("Login successful to %s", self._host)
        return True

    async def _api(self, payload: dict, retry: bool = True) -> dict:
        """Call authenticated API endpoint."""
        if not self._stok:
            await self.async_login()

        url = f"{self._base_url}/stok={self._stok}/ds"
        try:
            data = await self._post(url, payload)
        except asyncio.TimeoutError as err:
            raise TLAC100ConnectionError("Connection timeout") from err
        except aiohttp.ClientError as err:
            raise TLAC100ConnectionError(f"Connection error: {err}") from err

        error_code = data.get("error_code", 0)
        if error_code == -40401 and retry:
            _LOGGER.debug("Token expired, re-authenticating")
            self._stok = None
            await self.async_login()
            return await self._api(payload, retry=False)

        if error_code and error_code != 0:
            raise TLAC100ApiError(f"API error code: {error_code}")

        return data

    async def async_get_ap_list(self) -> list[dict[str, Any]]:
        """Get AP status list."""
        data = await self._api({
            "method": "get",
            "apmng_status": {
                "table": "ap_list",
                "filter": [{"group_id": ["0"], "ap_role": ["cap_all", "normal"]}],
                "para": {"start": 0, "end": 200},
            },
        })
        return _parse_list(data.get("apmng_status", {}).get("ap_list", []))

    async def async_get_model_list(self) -> dict[str, str]:
        """Get AP model list (id -> model_name)."""
        data = await self._api({
            "method": "get",
            "apmng_set": {"table": "model_list"},
        })
        result = {}
        for item in _parse_list(data.get("apmng_set", {}).get("model_list", [])):
            result[item["id"]] = _decode_val(item.get("model_name", ""))
        return result

    async def async_get_terminal_list(self) -> list[dict[str, Any]]:
        """Get terminal/host list."""
        data = await self._api({
            "method": "get",
            "host_management": {
                "table": "host_info",
                "filter": [{"group_id": ["-1"]}],
                "para": {"start": 0, "end": 500},
            },
        })
        return _parse_list(data.get("host_management", {}).get("host_info", []))

    async def async_disconnect_terminals(self, mac_list: list[str]) -> dict:
        """Disconnect terminals by MAC."""
        return await self._api({
            "method": "do",
            "host_management": {
                "disconnect": {"macList": mac_list},
            },
        })

    async def async_block_terminal(
        self, mac: str, hostname: str, blocked: bool = True
    ) -> dict:
        """Block or unblock a terminal."""
        return await self._api({
            "method": "set",
            "host_management": {
                "table": "host_info",
                "filter": [{"mac": mac}],
                "para": {
                    "blocked": "1" if blocked else "0",
                    "hostname": hostname,
                },
            },
        })

    async def async_test_connection(self) -> bool:
        """Test connection and authentication."""
        try:
            await self.async_login()
            return True
        except TLAC100ApiError:
            return False
