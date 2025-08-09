from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Expose only a safe 'Force refresh' hub-level button per device."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data.get("client")

    # Build one button per device we know about
    new: list[ButtonEntity] = []
    for dev_id, dev in (coordinator.data or {}).items():
        new.append(TermoWebRefreshButton(coordinator, dev_id))
    if new:
        async_add_entities(new)

    # If devices appear later, add a button then
    def _on_update():
        cur_ids = {e.unique_id for e in new}
        to_add: list[ButtonEntity] = []
        for dev_id, dev in (coordinator.data or {}).items():
            uid = f"{DOMAIN}:{dev_id}:refresh"
            if uid in cur_ids:
                continue
            to_add.append(TermoWebRefreshButton(coordinator, dev_id))
        if to_add:
            async_add_entities(to_add)

    coordinator.async_add_listener(_on_update)


class TermoWebRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button that requests an immediate coordinator refresh."""

    _attr_name = "Force refresh"
    _attr_has_entity_name = True

    def __init__(self, coordinator, dev_id: str) -> None:
        super().__init__(coordinator)
        self._dev_id = dev_id
        self._attr_unique_id = f"{DOMAIN}:{dev_id}:refresh"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._dev_id)})

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
