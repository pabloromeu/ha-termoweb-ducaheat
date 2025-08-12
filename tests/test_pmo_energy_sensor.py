from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

# Provide minimal Home Assistant stubs for module imports
ha_pkg = types.ModuleType("homeassistant")
core_mod = types.ModuleType("homeassistant.core")


class HomeAssistant:  # pragma: no cover - simple stub
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.loop = asyncio.get_event_loop()

    def async_create_task(self, coro):  # pragma: no cover - pass-through
        return self.loop.create_task(coro)


def callback(func):  # pragma: no cover - identity decorator
    return func


core_mod.HomeAssistant = HomeAssistant
core_mod.callback = callback

dispatcher_mod = types.ModuleType("homeassistant.helpers.dispatcher")


def async_dispatcher_send(hass, signal, payload) -> None:  # pragma: no cover
    for cb in hass.data.setdefault("_signals", {}).get(signal, []):
        cb(payload)


def async_dispatcher_connect(hass, signal, cb):  # pragma: no cover
    hass.data.setdefault("_signals", {}).setdefault(signal, []).append(cb)

    def _unsub() -> None:
        hass.data.get("_signals", {}).get(signal, []).remove(cb)

    return _unsub


dispatcher_mod.async_dispatcher_send = async_dispatcher_send
dispatcher_mod.async_dispatcher_connect = async_dispatcher_connect

update_mod = types.ModuleType("homeassistant.helpers.update_coordinator")


class UpdateFailed(Exception):  # pragma: no cover - simple placeholder
    pass


class DataUpdateCoordinator:  # pragma: no cover - minimal coordinator
    def __init__(self, hass, *, logger=None, name=None, update_interval=None) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data: Dict[str, Any] | None = None
        self._listeners: list = []

    __class_getitem__ = classmethod(lambda cls, _item: cls)

    async def async_config_entry_first_refresh(self) -> None:
        self.data = await self._async_update_data()

    def async_set_updated_data(self, data) -> None:
        self.data = data
        for cb in list(self._listeners):
            cb()

    def async_add_listener(self, cb) -> None:
        self._listeners.append(cb)


class CoordinatorEntity:  # pragma: no cover - simple base
    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator

    async def async_added_to_hass(self) -> None:  # pragma: no cover - no-op
        return None

    def async_on_remove(self, _func) -> None:  # pragma: no cover - no-op
        return None


update_mod.DataUpdateCoordinator = DataUpdateCoordinator
update_mod.UpdateFailed = UpdateFailed
update_mod.CoordinatorEntity = CoordinatorEntity

entity_mod = types.ModuleType("homeassistant.helpers.entity")


class DeviceInfo(dict):  # pragma: no cover - dict subclass
    pass


entity_mod.DeviceInfo = DeviceInfo

sensor_mod = types.ModuleType("homeassistant.components.sensor")


class SensorEntity:  # pragma: no cover - empty base
    pass


class SensorDeviceClass:  # pragma: no cover - enum placeholder
    POWER = "power"
    TEMPERATURE = "temperature"


class SensorStateClass:  # pragma: no cover - enum placeholder
    MEASUREMENT = "measurement"


sensor_mod.SensorEntity = SensorEntity
sensor_mod.SensorDeviceClass = SensorDeviceClass
sensor_mod.SensorStateClass = SensorStateClass

sys.modules.setdefault("homeassistant", ha_pkg)
sys.modules.setdefault("homeassistant.core", core_mod)
sys.modules.setdefault("homeassistant.helpers.dispatcher", dispatcher_mod)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", update_mod)
sys.modules.setdefault("homeassistant.helpers.entity", entity_mod)
sys.modules.setdefault("homeassistant.components.sensor", sensor_mod)

const_mod = types.ModuleType("homeassistant.const")


class UnitOfTemperature:  # pragma: no cover - placeholder
    CELSIUS = "°C"


const_mod.UnitOfTemperature = UnitOfTemperature
sys.modules.setdefault("homeassistant.const", const_mod)

# Minimal aiohttp stub
aiohttp_stub = types.ModuleType("aiohttp")


class ClientSession:  # pragma: no cover - placeholder
    pass


class ClientTimeout:  # pragma: no cover - placeholder
    def __init__(self, total: int | None = None) -> None:
        self.total = total


class ClientResponseError(Exception):  # pragma: no cover - placeholder
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args)


aiohttp_stub.ClientSession = ClientSession
aiohttp_stub.ClientTimeout = ClientTimeout
aiohttp_stub.ClientResponseError = ClientResponseError
aiohttp_stub.ClientError = Exception
sys.modules.setdefault("aiohttp", aiohttp_stub)

from custom_components.termoweb import sensor as sensor_mod  # noqa: E402
from custom_components.termoweb.api import TermoWebClient  # noqa: E402
from custom_components.termoweb.coordinator import (
    TermoWebPmoEnergyCoordinator,  # noqa: E402
)


class MockResponse:
    def __init__(
        self,
        status: int,
        json_data: Any,
        *,
        headers: Dict[str, str] | None = None,
        text_data: str = "",
    ) -> None:
        self.status = status
        self._json = json_data
        self._text = text_data
        self.headers = headers or {}
        self.request_info = None
        self.history = ()

    async def __aenter__(self) -> "MockResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no-op
        return None

    async def text(self) -> str:
        return self._text

    async def json(self, content_type: str | None = None) -> Any:  # pragma: no cover
        return self._json


def test_get_pmo_samples_request() -> None:
    async def _run() -> None:
        session = MagicMock()
        session.post.return_value = MockResponse(
            200,
            {"access_token": "tok", "expires_in": 3600},
            headers={"Content-Type": "application/json"},
        )
        session.request.return_value = MockResponse(
            200,
            {"samples": []},
            headers={"Content-Type": "application/json"},
        )
        client = TermoWebClient(session, "user", "pass")
        await client.get_pmo_samples("dev1", 2, start=0, end=10)
        method, url = session.request.call_args[0][:2]
        params = session.request.call_args[1]["params"]
        assert method == "GET"
        assert url.endswith("/api/v2/devs/dev1/pmo/2/samples")
        assert params == {"start": 0, "end": 10}

    asyncio.run(_run())


def test_energy_sensor_wh_to_kwh() -> None:
    async def _run() -> None:
        hass = HomeAssistant()
        base = MagicMock()
        base.data = {
            "dev1": {
                "nodes": {"nodes": [{"type": "pmo", "addr": "1"}]},
            }
        }
        client = MagicMock()
        client.get_pmo_samples = AsyncMock(return_value=[{"t": 1, "counter": "1200"}])
        coord = TermoWebPmoEnergyCoordinator(hass, client, base)
        await coord.async_config_entry_first_refresh()
        ent = sensor_mod.TermoWebPmoEnergyTotal(
            coord, "entry", "dev1", "1", "Energy", "uid"
        )
        assert ent.native_value == 1.2

    asyncio.run(_run())


def test_energy_sensor_empty_samples() -> None:
    async def _run() -> None:
        hass = HomeAssistant()
        base = MagicMock()
        base.data = {
            "dev1": {
                "nodes": {"nodes": [{"type": "pmo", "addr": "1"}]},
            }
        }
        client = MagicMock()
        client.get_pmo_samples = AsyncMock(return_value=[])
        coord = TermoWebPmoEnergyCoordinator(hass, client, base)
        await coord.async_config_entry_first_refresh()
        ent = sensor_mod.TermoWebPmoEnergyTotal(
            coord, "entry", "dev1", "1", "Energy", "uid"
        )
        assert ent.native_value is None

    asyncio.run(_run())


def test_energy_sensor_counter_reset() -> None:
    async def _run() -> None:
        hass = HomeAssistant()
        base = MagicMock()
        base.data = {
            "dev1": {
                "nodes": {"nodes": [{"type": "pmo", "addr": "1"}]},
                "pmo": {"energy": {"1": 1000.0}},
            }
        }
        client = MagicMock()
        client.get_pmo_samples = AsyncMock(
            side_effect=[[{"t": 1, "counter": "1000"}], [{"t": 2, "counter": "0"}]]
        )
        coord = TermoWebPmoEnergyCoordinator(hass, client, base)
        await coord.async_config_entry_first_refresh()
        coord.async_set_updated_data(await coord._async_update_data())
        ent = sensor_mod.TermoWebPmoEnergyTotal(
            coord, "entry", "dev1", "1", "Energy", "uid"
        )
        assert ent.native_value == 0.0

    asyncio.run(_run())
