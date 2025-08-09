from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, signal_ws_status
from .coordinator import TermoWebCoordinator


async def async_setup_entry(hass, entry, async_add_entities):
    coord: TermoWebCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    added_ids: set[str] = hass.data[DOMAIN][entry.entry_id].setdefault("added_binary_ids", set())

    @callback
    def _add_entities():
        new_entities = []
        for dev_id, data in (coord.data or {}).items():
            uid = f"{dev_id}_online"
            if uid in added_ids:
                continue
            new_entities.append(TermoWebDeviceOnlineBinarySensor(coord, entry.entry_id, dev_id))
            added_ids.add(uid)
        if new_entities:
            async_add_entities(new_entities)

    coord.async_add_listener(_add_entities)
    if coord.data:
        _add_entities()


class TermoWebDeviceOnlineBinarySensor(CoordinatorEntity[TermoWebCoordinator], BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: TermoWebCoordinator, entry_id: str, dev_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev_id = dev_id
        data = coordinator.data.get(dev_id, {})
        self._attr_name = f"{(data.get('name') or dev_id).strip()} Online"
        self._attr_unique_id = f"{dev_id}_online"
        self._unsub_ws = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Listen for WS status to expose diagnostics on the hub device entity
        self._unsub_ws = async_dispatcher_connect(
            self.hass, signal_ws_status(self._entry_id), self._on_ws_status
        )
        self.async_on_remove(lambda: self._unsub_ws() if self._unsub_ws else None)

    def _ws_state(self) -> dict[str, Any]:
        rec = self.hass.data[DOMAIN][self._entry_id]
        return (rec.get("ws_state") or {}).get(self._dev_id, {})  # status, last_event_at, healthy_minutes…

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data.get(self._dev_id, {})
        # connected may be True/False/None (unknown when endpoint 404s)
        return bool(data.get("connected"))

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self._dev_id, {})
        # Read version from manifest (stored at setup) to keep DRY with the manifest
        version = self.hass.data[DOMAIN][self._entry_id].get("version")
        return {
            "identifiers": {(DOMAIN, self._dev_id)},
            "name": (data.get("name") or self._dev_id).strip(),
            "manufacturer": "ATC / Termoweb",
            "model": data.get("raw", {}).get("model") or "Heater/Controller",
            "sw_version": version,
            "configuration_url": "https://control.termoweb.net",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self._dev_id, {})
        ws = self._ws_state()
        return {
            "dev_id": self._dev_id,
            "name": data.get("name"),
            "connected": data.get("connected"),
            "ws_status": ws.get("status"),
            "ws_last_event_at": ws.get("last_event_at"),
            "ws_healthy_minutes": ws.get("healthy_minutes"),
            "raw": data.get("raw") or {},
        }

    @callback
    def _on_ws_status(self, payload: dict) -> None:
        if payload.get("dev_id") != self._dev_id:
            return
        # Status changed; attributes may have changed too
        self.schedule_update_ha_state()
