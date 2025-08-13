from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import TermoWebClient
from .const import (
    API_BASE,
    DOMAIN,
    WS_NAMESPACE,
    signal_ws_data,
    signal_ws_status,
)

_LOGGER = logging.getLogger(__name__)

HandshakeResult = Tuple[str, int]  # (sid, heartbeat_timeout_s)


@dataclass
class WSStats:
    frames_total: int = 0
    events_total: int = 0
    last_event_ts: float = 0.0
    last_paths: List[str] | None = None


class TermoWebWSLegacyClient:
    """
    Minimal read-only Socket.IO 0.9 client for TermoWeb cloud.

    Behavior:
      - GET /socket.io/1/ handshake (with token/dev_id query)
      - WebSocket connect to /socket.io/1/websocket/<sid>?token=...&dev_id=...
      - Join namespace: "1::/api/v2/socket_io"
      - Send one snapshot request: 5::/api/v2/socket_io:{"name":"dev_data","args":[]}
      - Maintain heartbeat: reply/send "2::" periodically
      - Parse "5::/api/v2/socket_io:{...}" events; look for {"name":"data","args":[[{"path", "body"}, ...]]}
      - Normalize updates into coordinator.data and dispatch via HA dispatcher
      - Read-only: never sends control commands
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        dev_id: str,
        api_client: TermoWebClient,
        coordinator,  # TermoWebCoordinator; typed as Any to avoid import cycle
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.dev_id = dev_id
        self._client = api_client
        self._coordinator = coordinator
        self._session = session or api_client._session  # reuse HA session
        self._task: Optional[asyncio.Task] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

        self._closing = False
        self._connected_since: float | None = None
        self._healthy_since: float | None = None
        self._hb_send_interval: float = 27.0  # default; refined from handshake timeout
        self._hb_task: Optional[asyncio.Task] = None

        self._backoff_seq = [5, 10, 30, 120, 300]  # seconds
        self._backoff_idx = 0

        self._stats = WSStats()

    # ----------------- Public control -----------------

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._closing = False
        self._task = self.hass.loop.create_task(self._runner(), name=f"{DOMAIN}-ws-{self.dev_id}")
        return self._task

    async def stop(self) -> None:
        """Cancel tasks and close WS cleanly."""
        self._closing = True
        if self._hb_task:
            self._hb_task.cancel()
            try:
                await self._hb_task
            except asyncio.CancelledError:
                pass
            self._hb_task = None
        if self._ws:
            try:
                await self._ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message=b"client stop")
            except Exception:
                pass
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._update_status("stopped")

    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    # ----------------- Core loop -----------------

    async def _runner(self) -> None:
        self._update_status("starting")
        while not self._closing:
            try:
                sid, hb_timeout = await self._handshake()
                # keep client-side send interval well under server timeout
                self._hb_send_interval = max(5.0, min(30.0, hb_timeout * 0.45))
                await self._connect_ws(sid)
                await self._join_namespace()
                await self._send_snapshot_request()
                self._connected_since = time.time()
                self._healthy_since = None
                self._update_status("connected")

                # Start heartbeat sender
                self._hb_task = self.hass.loop.create_task(self._heartbeat_loop())

                # Read until disconnect
                await self._read_loop()

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Avoid noisy logs; just one INFO per failure with brief cause.
                _LOGGER.info("WS %s: connection error (%s); will retry", self.dev_id, type(e).__name__)
            finally:
                # Clean up this attempt
                if self._hb_task:
                    self._hb_task.cancel()
                    self._hb_task = None
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                self._update_status("disconnected")

                if self._closing:
                    break

                # Backoff with jitter
                delay = self._backoff_seq[min(self._backoff_idx, len(self._backoff_seq) - 1)]
                self._backoff_idx = min(self._backoff_idx + 1, len(self._backoff_seq) - 1)
                jitter = random.uniform(0.8, 1.2)
                await asyncio.sleep(delay * jitter)

        # End loop
        self._update_status("stopped")

    # ----------------- Protocol steps -----------------

    async def _handshake(self) -> HandshakeResult:
        """
        GET /socket.io/1/?token=<Bearer>&dev_id=<dev_id>&t=<ms>
        Returns: <sid>:<hb>:<disc>:websocket,xhr-polling
        """
        token = await self._get_token()
        t_ms = int(time.time() * 1000)
        url = f"{API_BASE}/socket.io/1/?token={token}&dev_id={self.dev_id}&t={t_ms}"

        async with asyncio.timeout(15):
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                body = await resp.text()
                if resp.status == 401:
                    # Token expired; refresh once and retry
                    _LOGGER.info("WS %s: handshake 401; refreshing token", self.dev_id)
                    await self._force_refresh_token()
                    token = await self._get_token()
                    url = f"{API_BASE}/socket.io/1/?token={token}&dev_id={self.dev_id}&t={int(time.time()*1000)}"
                    async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                        body = await resp2.text()
                        if resp2.status >= 400:
                            raise RuntimeError(f"handshake failed (status={resp2.status})")
                        sid, hb = self._parse_handshake_body(body)
                        self._backoff_idx = 0  # success resets backoff
                        return sid, hb

                if resp.status >= 400:
                    raise RuntimeError(f"handshake failed (status={resp.status})")

                sid, hb = self._parse_handshake_body(body)
                self._backoff_idx = 0  # success resets backoff
                return sid, hb

    async def _connect_ws(self, sid: str) -> None:
        token = await self._get_token()
        ws_url = f"{API_BASE.replace('https://', 'wss://')}/socket.io/1/websocket/{sid}?token={token}&dev_id={self.dev_id}"
        self._ws = await self._session.ws_connect(
            ws_url,
            heartbeat=None,  # we implement our own '2::' heartbeats
            timeout=15,
            autoclose=True,
            autoping=False,
            compress=0,
            protocols=("websocket",),
        )

    async def _join_namespace(self) -> None:
        await self._send_text(f"1::{WS_NAMESPACE}")

    async def _send_snapshot_request(self) -> None:
        # 5::/api/v2/socket_io:{"name":"dev_data","args":[]}
        payload = {"name": "dev_data", "args": []}
        await self._send_text(f"5::{WS_NAMESPACE}:{json.dumps(payload, separators=(',', ':'))}")

    # ----------------- Loops -----------------

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._hb_send_interval)
                await self._send_text("2::")
        except asyncio.CancelledError:
            return
        except Exception:
            # Sending heartbeat failed; the read loop will notice soon.
            return

    async def _read_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return

        while True:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.CLOSED:
                raise RuntimeError("ws closed")
            if msg.type == aiohttp.WSMsgType.CLOSE:
                raise RuntimeError("ws closing")
            if msg.type == aiohttp.WSMsgType.ERROR:
                raise RuntimeError("ws error")
            if msg.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                continue

            data = msg.data if isinstance(msg.data, str) else msg.data.decode("utf-8", "ignore")
            self._stats.frames_total += 1

            # Socket.IO 0.9 frames
            if data.startswith("2::"):
                # Heartbeat from server; track liveness
                self._mark_event(paths=None)
                continue
            if data.startswith(f"1::{WS_NAMESPACE}"):
                # Namespace ack; nothing to do
                continue
            if data.startswith(f"5::{WS_NAMESPACE}:"):
                try:
                    js = json.loads(data.split(f"5::{WS_NAMESPACE}:", 1)[1])
                except Exception:
                    continue
                self._handle_event(js)
                continue
            if data.startswith("0::"):
                # Disconnect
                raise RuntimeError("server disconnect")
            # ignore other frame types

    # ----------------- Event handling -----------------

    def _handle_event(self, evt: Dict[str, Any]) -> None:
        """
        Expecting: {"name": "data", "args": [ [ {"path": "...", "body": {...}}, ... ] ]}
        """
        if not isinstance(evt, dict):
            return
        name = evt.get("name")
        args = evt.get("args")
        if name != "data" or not isinstance(args, list) or not args:
            return
        batch = args[0] if isinstance(args[0], list) else None
        if not isinstance(batch, list):
            return

        paths: List[str] = []
        # Apply updates to coordinator.data in-place to keep shape compatible with current entities.
        updated_nodes = False
        updated_addrs: List[str] = []
        updated_pmo_power: List[str] = []

        for item in batch:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            body = item.get("body")
            if not isinstance(path, str):
                continue
            paths.append(path)

            # Normalize
            dev_map: Dict[str, Any] = (self._coordinator.data or {}).get(self.dev_id) or {}
            if not dev_map:
                # Seed minimal structure if coordinator has not put this dev yet
                dev_map = {
                    "dev_id": self.dev_id,
                    "name": f"Device {self.dev_id}",
                    "raw": {},
                    "connected": True,
                    "nodes": None,
                    "htr": {"addrs": [], "settings": {}},
                }
                # put into coordinator cache
                cur = dict(self._coordinator.data or {})
                cur[self.dev_id] = dev_map
                # Not calling async_set_updated_data: we dispatch directly after write.
                self._coordinator.data = cur  # type: ignore[attr-defined]

            # Routes
            if path.endswith("/mgr/nodes"):
                # body is nodes payload
                if isinstance(body, dict):
                    dev_map["nodes"] = body
                    # keep addrs in sync
                    addrs: list[str] = []
                    nl = body.get("nodes")
                    if isinstance(nl, list):
                        for n in nl:
                            if isinstance(n, dict) and (n.get("type") or "").lower() == "htr":
                                addrs.append(str(n.get("addr")))
                    dev_map.setdefault("htr", {}).setdefault("settings", {})
                    dev_map["htr"]["addrs"] = addrs
                    updated_nodes = True

            elif "/htr/" in path and path.endswith("/settings"):
                # /api/v2/devs/{dev_id}/htr/{addr}/settings => push path uses '/htr/<addr>/settings'
                addr = path.split("/htr/")[1].split("/")[0]
                settings_map: Dict[str, Any] = dev_map.setdefault("htr", {}).setdefault("settings", {})
                if isinstance(body, dict):
                    settings_map[addr] = body
                    updated_addrs.append(addr)

            elif "/htr/" in path and path.endswith("/advanced_setup"):
                # Store for diagnostics/future; entities ignore for now
                addr = path.split("/htr/")[1].split("/")[0]
                adv_map: Dict[str, Any] = dev_map.setdefault("htr", {}).setdefault("advanced", {})
                if isinstance(body, dict):
                    adv_map[addr] = body

            elif "/pmo/" in path and path.endswith("/power"):
                addr = path.split("/pmo/")[1].split("/")[0]
                power_map: Dict[str, Any] = dev_map.setdefault("pmo", {}).setdefault("power", {})
                val = None
                if isinstance(body, dict):
                    body = body.get("power")
                try:
                    if body is not None:
                        val = float(body)
                except Exception:
                    val = None
                if val is not None:
                    power_map[addr] = val
                    updated_pmo_power.append(addr)

            else:
                # Other top-level paths, store compactly under raw
                raw = dev_map.setdefault("raw", {})
                key = path.strip("/").replace("/", "_")
                raw[key] = body

        # Dispatch (one compact signal)
        self._mark_event(paths=paths)
        payload_base = {"dev_id": self.dev_id, "ts": self._stats.last_event_ts}
        if updated_nodes:
            async_dispatcher_send(self.hass, signal_ws_data(self.entry_id), {**payload_base, "addr": None, "kind": "nodes"})
        for addr in set(updated_addrs):
            async_dispatcher_send(self.hass, signal_ws_data(self.entry_id), {**payload_base, "addr": addr, "kind": "htr_settings"})
        for addr in set(updated_pmo_power):
            async_dispatcher_send(self.hass, signal_ws_data(self.entry_id), {**payload_base, "addr": addr, "kind": "pmo_power"})

    # ----------------- Helpers -----------------

    def _parse_handshake_body(self, body: str) -> HandshakeResult:
        # "<sid>:<heartbeat>:<disconnect>:<transports>"
        parts = (body or "").strip().split(":")
        if len(parts) < 2:
            raise RuntimeError("handshake malformed")
        sid = parts[0]
        try:
            hb = int(parts[1])
        except Exception:
            hb = 60
        return sid, hb

    async def _send_text(self, data: str) -> None:
        if not self._ws:
            return
        await self._ws.send_str(data)

    async def _get_token(self) -> str:
        # Borrow token from API client without logging it
        headers = await self._client._authed_headers()
        return headers["Authorization"].split(" ", 1)[1]

    async def _force_refresh_token(self) -> None:
        # Clear cached token and fetch a new one
        try:
            # noinspection PyUnresolvedReferences
            self._client._access_token = None  # type: ignore[attr-defined]
        except Exception:
            pass
        await self._client._ensure_token()

    def _update_status(self, status: str) -> None:
        # Update shared state bucket (hass.data[...] managed by integration)
        state_bucket = self.hass.data[DOMAIN][self.entry_id].setdefault("ws_state", {})
        s = state_bucket.setdefault(self.dev_id, {})
        now = time.time()
        s["status"] = status
        s["last_event_at"] = self._stats.last_event_ts or None
        s["healthy_since"] = self._healthy_since
        s["healthy_minutes"] = int(((now - self._healthy_since) / 60)) if self._healthy_since else 0
        s["frames_total"] = self._stats.frames_total
        s["events_total"] = self._stats.events_total

        # Dispatch a status update so the hub entity & setup logic can react (e.g., stretch polling)
        async_dispatcher_send(self.hass, signal_ws_status(self.entry_id), {"dev_id": self.dev_id, "status": status})

    def _mark_event(self, *, paths: Optional[List[str]]) -> None:
        now = time.time()
        self._stats.last_event_ts = now
        if paths:
            self._stats.events_total += 1
            if _LOGGER.isEnabledFor(logging.DEBUG):
                # Keep only first few distinct paths for compact debug
                uniq = []
                for p in paths:
                    if p not in uniq:
                        uniq.append(p)
                    if len(uniq) >= 5:
                        break
                self._stats.last_paths = uniq

        # Health heuristic: connected and alive for ≥ 300s => healthy
        if self._connected_since and not self._healthy_since and (now - self._connected_since) >= 300:
            self._healthy_since = now
            self._update_status("healthy")
