from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_USERNAME, CONF_PASSWORD, CONF_BASE_URL, CONF_BASIC_B64, CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
)
from .api import DucaheatApi

_LOGGER = logging.getLogger(__name__)

__all__ = ["DucaheatCoordinator"]


HEATER_TYPES = {"htr", "acm"}  # <-- accept ACM as heater type


class DucaheatCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls devices/nodes using the v2 API and exposes heater nodes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        session = aiohttp_client.async_get_clientsession(hass)
        self.api = DucaheatApi(
            session,
            base_url=entry.data[CONF_BASE_URL],
            basic_b64=(entry.data.get(CONF_BASIC_B64) or None),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=int(entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            await self.api.login(self.entry.data[CONF_USERNAME], self.entry.data[CONF_PASSWORD])
        except Exception as err:
            raise UpdateFailed(f"auth failed: {err}") from err

        entities: list[dict[str, Any]] = []

        # Devices
        try:
            devs = await self.api.list_devices()
        except Exception as err:
            _LOGGER.debug("list_devices failed: %s", err)
            devs = []

        for d in devs or []:
            dev_id = str(d.get("dev_id") or d.get("id") or "")
            dev_name = d.get("name") or f"Dev {dev_id}"
            if not dev_id:
                continue

            # Nodes for each device
            try:
                nodes = await self.api.list_nodes(dev_id)
                _LOGGER.debug("list_nodes succeed: %s", dev_id)
            except Exception as err:
                _LOGGER.debug("list_nodes(%s) failed: %s", dev_id, err)
                nodes = []

            for n in nodes or []:
                # normalize keys
                ntype = (n.get("type") or n.get("Type") or n.get("node_type") or "").lower()
                if ntype not in HEATER_TYPES:
                    continue
                addr = n.get("addr") or n.get("Direccion") or n.get("address") or n.get("id")
                if addr is None:
                    continue
                addr_str = str(addr)
                name = n.get("name") or n.get("Nombre") or f"Heater {addr_str}"
                try:
                    settings = await self.api.get_node_settings(dev_id, ntype, addr_str)
                    _LOGGER.debug("node (%s/%s/%s) settings succeed: %s",dev_id, ntype,addr_str, dev_id)
                except Exception as err:
                    _LOGGER.debug("get_node_settings(%s, %s, %s) failed: %s", dev_id, ntype, addr_str, err)
                    settings = {}
                entities.append({
                    "dev_id": dev_id,
                    "dev_name": dev_name,
                    "node_type": ntype,       # <--- keep node type for climate
                    "addr": addr_str,
                    "name": name,
                    "settings": settings,
                })

        _LOGGER.debug("devices/nodes produced %s entities%s",
                      len(entities),
                      f" (first={entities[0]})" if entities else "")
        return {"entities": entities}