from __future__ import annotations

from typing import Any, Set

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_BOOST_MINUTES, DEFAULT_BOOST_MINUTES
from .coordinator import DucaheatCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coord: DucaheatCoordinator = store["coordinator"]

    added: Set[str] = store.setdefault("climate_added", set())

    @callback
    def _discover_new() -> None:
        to_add: list[DucaheatClimate] = []
        for e in (coord.data or {}).get("entities", []):
            uid = f"{e['dev_id']}-{e['node_type']}-{e['addr']}"
            if uid in added:
                continue
            ent = DucaheatClimate(coord, e["dev_id"], e["node_type"], e["addr"], e.get("name") or uid, entry)
            to_add.append(ent)
            added.add(uid)
        if to_add:
            add_entities(to_add)

    _discover_new()
    coord.async_add_listener(_discover_new)


class DucaheatClimate(CoordinatorEntity[DucaheatCoordinator], ClimateEntity):
    """Heater entity: current temp via mtemp, set temp via Boost, mode via /mode."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = ["auto", "boost", "off"]

    def __init__(self, coordinator: DucaheatCoordinator, dev_id: str, node_type: str, addr: str, name: str, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._dev_id = dev_id
        self._node_type = node_type
        self._addr = addr
        self._attr_name = name
        self._attr_unique_id = f"{dev_id}-{node_type}-{addr}"
        self._entry = entry

    # -------- Helpers --------
    def _settings(self) -> dict[str, Any]:
        for e in (self.coordinator.data or {}).get("entities", []):
            if e["dev_id"] == self._dev_id and e["node_type"] == self._node_type and e["addr"] == self._addr:
                return e.get("settings") or {}
        return {}

    # -------- Properties (read) --------
    @property
    def hvac_mode(self) -> HVACMode:
        s = self._settings()
        # Treat Boost as actively heating regardless of reported "mode"
        if bool(s.get("boost")):
            return HVACMode.HEAT
        mode = (s.get("mode") or "").lower()
        # Some firmwares report "off" even when boost true; handled above.
        return HVACMode.OFF if mode in ("off", "frost") else HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        s = self._settings()
        # Show "boost" when boost flag is set, even if mode says "off"
        if bool(s.get("boost")):
            return "boost"
        val = s.get("mode")
        return val.lower() if isinstance(val, str) else None

    @property
    def current_temperature(self) -> float | None:
        s = self._settings()
        mt = s.get("mtemp")
        try:
            return float(mt)
        except Exception:
            return None

    @property
    def target_temperature(self) -> float | None:
        s = self._settings()
        t = s.get("stemp")
        try:
            return float(t)
        except Exception:
            return None

    # -------- Commands (write) --------
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        mode = "off" if hvac_mode == HVACMode.OFF else "manual"
        try:
            s = self._settings()
            # Show "boost" when boost flag is set, even if mode says "off"
            if hvac_mode==HVACMode.OFF and bool(s.get("boost")):
                self.coordinator.logger.debug("set_hvac_mode %s: %s", hvac_mode, s.get("boost"))
                await self.coordinator.api.set_boost(self._dev_id, self._node_type, self._addr, boost=False, stemp_c=float(10.0), minutes=10)
            else:
                await self.coordinator.api.set_mode(self._dev_id, self._node_type, self._addr, mode)
        except Exception as exc:
            self.coordinator.logger.debug("set_hvac_mode failed for %s/%s: %s", self._node_type, self._addr, exc)
            return
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        try:
            s = self._settings()
            # Show "boost" when boost flag is set, even if mode says "off"
            if preset_mode== "off" and bool(s.get("boost")):
                self.coordinator.logger.debug("async_set_preset_mode %s: %s", preset_mode, s.get("boost"))
                await self.coordinator.api.set_boost(self._dev_id, self._node_type, self._addr, boost=False,stemp_c=float(10.0), minutes=10)
            else:
                await self.coordinator.api.set_mode(self._dev_id, self._node_type, self._addr, preset_mode)
        except Exception as exc:
            self.coordinator.logger.debug("set_preset_mode failed for %s/%s: %s", self._node_type, self._addr, exc)
            return
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Implement set temperature by issuing a BOOST with configured duration."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        minutes = int(self._entry.options.get(CONF_BOOST_MINUTES, DEFAULT_BOOST_MINUTES))
        try:
            await self.coordinator.api.set_boost(self._dev_id, self._node_type, self._addr, boost=True, stemp_c=float(temp), minutes=minutes)
        except Exception as exc:
            self.coordinator.logger.debug("set_temperature/boost failed for %s/%s: %s", self._node_type, self._addr, exc)
            return
        await self.coordinator.async_request_refresh()