from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
import logging
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, signal_ws_status
from .coordinator import TermoWebCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up one connectivity binary sensor per TermoWeb hub (dev_id)."""
    coord: TermoWebCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    added_ids: set[str] = hass.data[DOMAIN][entry.entry_id].setdefault(
        "added_binary_ids", set()
    )

    @callback
    def _add_entities() -> None:
        # Add exactly one sensor per dev_id (the hub)
        for dev_id, _data in (coord.data or {}).items():
            uid = f"{dev_id}_online"
            if uid in added_ids:
                continue
            try:
                ent = TermoWebDeviceOnlineBinarySensor(coord, entry.entry_id, dev_id)
                async_add_entities([ent])
                added_ids.add(uid)
            except Exception as exc:
                _LOGGER.error("Failed to add hub binary sensor dev_id=%s: %s", dev_id, exc)

    coord.async_add_listener(_add_entities)
    if coord.data:
        _add_entities()


class TermoWebDeviceOnlineBinarySensor(
    CoordinatorEntity[TermoWebCoordinator], BinarySensorEntity
):
    """Connectivity sensor for the TermoWeb hub (gateway)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, coordinator: TermoWebCoordinator, entry_id: str, dev_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev_id = str(dev_id)
        data = coordinator.data.get(self._dev_id, {}) or {}
        base_name = (data.get("name") or self._dev_id)
        try:
            base_name = str(base_name).strip()
        except Exception:
            base_name = str(self._dev_id)
        self._attr_name = f"{base_name} Online"
        self._attr_unique_id = f"{self._dev_id}_online"
        self._unsub_ws = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_ws = async_dispatcher_connect(
            self.hass, signal_ws_status(self._entry_id), self._on_ws_status
        )
        self.async_on_remove(lambda: self._unsub_ws() if self._unsub_ws else None)

    def _ws_state(self) -> dict[str, Any]:
        rec = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        return (rec.get("ws_state") or {}).get(self._dev_id, {})

    @property
    def is_on(self) -> bool:
        data = (self.coordinator.data or {}).get(self._dev_id, {}) or {}
        return bool(data.get("connected"))

    @property
    def device_info(self) -> DeviceInfo:
        data = (self.coordinator.data or {}).get(self._dev_id, {}) or {}
        version = (self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}).get("version")
        model = (data.get("raw") or {}).get("model") or "Gateway/Controller"
        name = (data.get("name") or self._dev_id)
        try:
            name = str(name).strip()
        except Exception:
            name = str(self._dev_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self._dev_id)},
            name=name,
            manufacturer="ATC / Termoweb",
            model=str(model),
            sw_version=str(version) if version is not None else None,
            configuration_url="https://control.termoweb.net",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.coordinator.data or {}).get(self._dev_id, {}) or {}
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
        self.schedule_update_ha_state()
