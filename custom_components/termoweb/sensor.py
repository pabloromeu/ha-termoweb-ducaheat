from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, signal_ws_data
from .coordinator import TermoWebPmoEnergyCoordinator, TermoWebPmoPowerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up temperature sensors for each heater node."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    pmo_coord = TermoWebPmoPowerCoordinator(hass, client, coordinator, entry.entry_id)
    data["pmo_power_coordinator"] = pmo_coord
    await pmo_coord.async_config_entry_first_refresh()
    pmo_energy_coord = TermoWebPmoEnergyCoordinator(hass, client, coordinator)
    data["pmo_energy_coordinator"] = pmo_energy_coord
    await pmo_energy_coord.async_config_entry_first_refresh()

    added: set[str] = set()

    async def build_and_add() -> None:
        new_entities: list[SensorEntity] = []
        data_now = coordinator.data or {}
        for dev_id, dev in data_now.items():
            nodes = dev.get("nodes") or {}
            node_list = nodes.get("nodes") if isinstance(nodes, dict) else None
            if not isinstance(node_list, list):
                continue

            for node in node_list:
                if not isinstance(node, dict):
                    continue
                ntype = (node.get("type") or "").lower()
                addr = str(node.get("addr"))
                base_name = (node.get("name") or f"Node {addr}").strip() or f"Node {addr}"
                if ntype == "htr":
                    unique_id = f"{DOMAIN}:{dev_id}:htr:{addr}:temp"
                    if unique_id in added:
                        continue
                    ent_name = f"{base_name} Temperature"
                    new_entities.append(
                        TermoWebHeaterTemp(
                            coordinator, entry.entry_id, dev_id, addr, ent_name, unique_id
                        )
                    )
                    added.add(unique_id)

                    power_map = (
                        (pmo_coord.data or {})
                        .get(dev_id, {})
                        .get("pmo", {})
                        .get("power", {})
                    )
                    energy_map = (
                        (pmo_energy_coord.data or {})
                        .get(dev_id, {})
                        .get("pmo", {})
                        .get("energy", {})
                    )
                    has_power = addr in power_map
                    has_energy = addr in energy_map
                    if has_power or has_energy:
                        _LOGGER.debug(
                            "PMO data found for heater %s/%s: power=%s energy=%s",
                            dev_id,
                            addr,
                            has_power,
                            has_energy,
                        )
                        if has_power:
                            unique_id_p = f"{DOMAIN}:{dev_id}:pmo:{addr}:power"
                            if unique_id_p not in added:
                                ent_name_p = f"{base_name} Power"
                                new_entities.append(
                                    TermoWebPmoPower(
                                        pmo_coord,
                                        entry.entry_id,
                                        dev_id,
                                        addr,
                                        ent_name_p,
                                        unique_id_p,
                                    )
                                )
                                added.add(unique_id_p)
                        if has_energy:
                            unique_id_energy = f"{dev_id}:{addr}:energy"
                            if unique_id_energy not in added:
                                ent_name_energy = f"{base_name} Energy Total"
                                new_entities.append(
                                    TermoWebPmoEnergyTotal(
                                        pmo_energy_coord,
                                        entry.entry_id,
                                        dev_id,
                                        addr,
                                        ent_name_energy,
                                        unique_id_energy,
                                    )
                                )
                                added.add(unique_id_energy)
                    else:
                        _LOGGER.debug(
                            "No PMO data for heater %s/%s", dev_id, addr
                        )
                elif ntype == "pmo":
                    unique_id = f"{DOMAIN}:{dev_id}:pmo:{addr}:power"
                    if unique_id in added:
                        continue
                    ent_name = f"{base_name} Power"
                    new_entities.append(
                        TermoWebPmoPower(
                            pmo_coord, entry.entry_id, dev_id, addr, ent_name, unique_id
                        )
                    )
                    added.add(unique_id)
                    unique_id_energy = f"{dev_id}:{addr}:energy"
                    if unique_id_energy not in added:
                        ent_name_energy = f"{base_name} Energy Total"
                        new_entities.append(
                            TermoWebPmoEnergyTotal(
                                pmo_energy_coord,
                                entry.entry_id,
                                dev_id,
                                addr,
                                ent_name_energy,
                                unique_id_energy,
                            )
                        )
                        added.add(unique_id_energy)

        if new_entities:
            _LOGGER.debug("Adding %d TermoWeb sensors", len(new_entities))
            async_add_entities(new_entities)

    # Add now and on subsequent coordinator updates
    await build_and_add()

    def _on_coordinator_update() -> None:
        hass.async_create_task(build_and_add())

    coordinator.async_add_listener(_on_coordinator_update)


class TermoWebHeaterTemp(CoordinatorEntity, SensorEntity):
    """Temperature sensor for a single heater node (read-only mtemp)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, entry_id: str, dev_id: str, addr: str, name: str, unique_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev_id = dev_id
        self._addr = addr
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._unsub_ws = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_ws = async_dispatcher_connect(
            self.hass, signal_ws_data(self._entry_id), self._on_ws_data
        )
        self.async_on_remove(lambda: self._unsub_ws() if self._unsub_ws else None)

    @property
    def device_info(self) -> DeviceInfo:
        # Attach to the existing hub device (like climate + button)
        return DeviceInfo(identifiers={(DOMAIN, self._dev_id)})

    def _settings(self) -> dict[str, Any] | None:
        d = (self.coordinator.data or {}).get(self._dev_id, {})
        htr = d.get("htr") or {}
        settings = (htr.get("settings") or {}).get(self._addr)
        return settings if isinstance(settings, dict) else None

    @staticmethod
    def _f(val: Any) -> Optional[float]:
        try:
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).strip()
            return float(s) if s else None
        except Exception:
            return None

    @callback
    def _on_ws_data(self, payload: dict) -> None:
        if payload.get("dev_id") != self._dev_id:
            return
        addr = payload.get("addr")
        if addr is not None and str(addr) != self._addr:
            return
        # Thread-safe state update
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        d = (self.coordinator.data or {}).get(self._dev_id, {})
        return d.get("nodes") is not None

    @property
    def native_value(self) -> Optional[float]:
        s = self._settings() or {}
        return self._f(s.get("mtemp"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._settings() or {}
        return {
            "dev_id": self._dev_id,
            "addr": self._addr,
            "units": s.get("units"),
        }


class TermoWebPmoPower(CoordinatorEntity, SensorEntity):
    """Power sensor for PMO nodes."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(
        self,
        coordinator: TermoWebPmoPowerCoordinator,
        entry_id: str,
        dev_id: str,
        addr: str,
        name: str,
        unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev_id = dev_id
        self._addr = addr
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._unsub_ws = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_ws = async_dispatcher_connect(
            self.hass, signal_ws_data(self._entry_id), self._on_ws_data
        )
        self.async_on_remove(lambda: self._unsub_ws() if self._unsub_ws else None)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._dev_id)})

    @callback
    def _on_ws_data(self, payload: dict) -> None:
        if payload.get("kind") != "pmo_power":
            return
        if payload.get("dev_id") != self._dev_id:
            return
        addr = payload.get("addr")
        if addr is not None and addr != self._addr:
            return
        self.schedule_update_ha_state()

    @property
    def native_value(self) -> Optional[float]:
        dev = (self.coordinator.data or {}).get(self._dev_id, {})
        return (
            dev.get("pmo", {})
            .get("power", {})
            .get(self._addr)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "dev_id": self._dev_id,
            "addr": self._addr,
        }


class TermoWebPmoEnergyTotal(CoordinatorEntity, SensorEntity):
    """Total energy sensor for PMO nodes."""

    _attr_state_class = "total_increasing"
    _attr_native_unit_of_measurement = "kWh"

    def __init__(
        self,
        coordinator: TermoWebPmoEnergyCoordinator,
        entry_id: str,
        dev_id: str,
        addr: str,
        name: str,
        unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev_id = dev_id
        self._addr = addr
        self._attr_name = name
        self._attr_unique_id = unique_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._dev_id)})

    @property
    def native_value(self) -> Optional[float]:
        dev = (self.coordinator.data or {}).get(self._dev_id, {})
        val = dev.get("pmo", {}).get("energy", {}).get(self._addr)
        return val / 1000.0 if val is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"dev_id": self._dev_id, "addr": self._addr}
