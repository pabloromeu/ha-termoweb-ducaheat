from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .const import USER_AGENT, ACCEPT_LANGUAGE, DUCAHEAT_BASIC_AUTH_B64

_LOGGER = logging.getLogger(__name__)


class DucaheatApi:
    """Async client for the Ducaheat (tevolve) REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        base_url: str,
        basic_b64: Optional[str] = None,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._api = f"{self._base}/api/v2"
        self._token_url = f"{self._base}/client/token"
        self._basic = (basic_b64 or DUCAHEAT_BASIC_AUTH_B64 or "").strip()
        self._access: Optional[str] = None
        self._refresh: Optional[str] = None
        self._exp_ts: float = 0.0

    # ---------- Auth ----------
    async def login(self, username: str, password: str) -> None:
        now = time.time()
        if self._access and now < self._exp_ts:
            return
        if not self._basic:
            raise RuntimeError("Missing Basic client header")
        if self._refresh and now >= self._exp_ts:
            try:
                await self._token(grant_type="refresh_token", refresh_token=self._refresh)
                return
            except Exception as exc:
                _LOGGER.debug("Refresh failed, retrying password grant: %s", exc)
        await self._token(grant_type="password", username=username, password=password)

    async def _token(self, **form: str) -> None:
        headers = {
            "Authorization": f"Basic {self._basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        _LOGGER.debug("Token POST %s", self._token_url)
        async with self._session.post(
            self._token_url, data=form, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            data = await resp.json(content_type=None)
            _LOGGER.debug(
                "Token resp status=%s body_keys=%s",
                resp.status,
                list(data.keys()) if isinstance(data, dict) else type(data),
            )
            if resp.status >= 400:
                raise RuntimeError(f"token error {resp.status}: {data}")
        self._access = data.get("access_token")
        self._refresh = data.get("refresh_token")
        expires_in = int((data.get("expires_in") or 3600))
        self._exp_ts = time.time() + expires_in * 0.9

    async def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Accept-Language": ACCEPT_LANGUAGE,
        }

    # ---------- HTTP helpers ----------
    async def _get(self, url: str, *, params: Dict[str, Any] | None = None) -> Any:
        headers = await self._headers()
        async with self._session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"GET {url} -> {resp.status} {await resp.text()}")
            return await resp.json(content_type=None)

    async def _post(self, url: str, *, json: Dict[str, Any] | None = None) -> Any:
        headers = await self._headers()
        headers["Content-Type"] = "application/json"
        async with self._session.post(url, headers=headers, json=json, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"POST {url} -> {resp.status} {await resp.text()}")
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                return await resp.json(content_type=None)
            return await resp.text()

    # ---------- Public endpoints (v2) ----------
    async def list_devices(self) -> List[Dict[str, Any]]:
        """GET /api/v2/devs/"""
        url = f"{self._api}/devs/"
        data = await self._get(url)
        if isinstance(data, list):
            return data
        return data.get("devs") or data.get("devices") or data.get("items") or []

    async def list_nodes(self, dev_id: str) -> List[Dict[str, Any]]:
        """GET /api/v2/devs/{dev_id}/mgr/nodes"""
        url = f"{self._api}/devs/{dev_id}/mgr/nodes"
        data = await self._get(url)
        if isinstance(data, list):
            return data
        return data.get("nodes") or data.get("items") or data.get("data") or []

    async def get_node_settings(self, dev_id: str, node_type: str, addr: str | int) -> Dict[str, Any]:
        """GET /api/v2/devs/{dev_id}/{node_type}/{addr}/settings  (node_type e.g. 'acm', 'htr')"""
        url = f"{self._api}/devs/{dev_id}/{node_type}/{addr}/status"
        return await self._get(url)

    async def set_mode(self, dev_id: str, node_type: str, addr: str | int, mode: str) -> Any:
        """POST /api/v2/devs/{dev_id}/{node_type}/{addr}/mode with {"mode": "<value>"}"""
        addr = str(addr)
        url = f"{self._api}/devs/{dev_id}/{node_type}/{addr}/mode"
        return await self._post(url, json={"mode": mode})

    async def set_boost(self, dev_id: str, node_type: str, addr: str | int, *, boost: bool = True, stemp_c: float, minutes: int) -> Any:
        """
        Set a temporary setpoint via /boost.
        Server expects:
          {"boost": true, "stemp": "21.5", "units": "C", "boost_time": 60}
        """
        addr = str(addr)
        url = f"{self._api}/devs/{dev_id}/{node_type}/{addr}/boost"
        body = {
            "boost": boost,
            "stemp": f"{float(stemp_c):.1f}",
            "units": "C",
            "boost_time": int(minutes),
        }
        return await self._post(url, json=body)