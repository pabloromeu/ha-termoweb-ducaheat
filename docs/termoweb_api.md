# TermoWeb Cloud API — Confirmed Subset (updated 2025-08-10)

**Scope**  
This document lists only the endpoints and fields we have verified end-to-end from the Android app and live traffic, sufficient for the Home Assistant integration.

## Base
- Host: `https://control.termoweb.net`
- JSON everywhere.
- Typical headers (not required, but good hygiene):
  - `User-Agent: TermoWeb/2.5.1 (HomeAssistant Integration)`
  - `Accept-Language: en-IE,en;q=0.8`
  - `Accept: application/json`

## Auth
**POST `/client/token`** (basic client auth) → 200 JSON
- Request body (form-encoded): `username`, `password`, `grant_type=password`
- Response: `{ "access_token": "<opaque>" }`
- Use `Authorization: Bearer <access_token>` for subsequent requests.

---

## Devices and heaters

### Get heater settings
**GET `/api/v2/devs/{dev_id}/htr/{addr}/settings`** → 200 JSON

Representative shape (additional fields may be present):
```json
{
  "name": "Heater 1",
  "state": "on",
  "mode": "auto",             // "auto"|"manual"|"off"
  "units": "C",               // "C"|"F"
  "stemp": "21.0",            // may appear as string or number server-side
  "mtemp": "20.8",
  "ptemp": ["10.0","22.0","23.0"],   // presets: [cold, night, day]
  "prog":  [0,0,0,0,0,0,0, 1,1,2,2,2, ... 168 values ...],
  "priority": 1,
  "max_power": 1000,
  "addr": 1
}
```

**Schedule semantics (`prog`)**
- `prog` is a **168-element** array of integers, one per hour for a 7×24 week grid.
- **Indexing:** index `0` maps to **Monday 00:00–01:00**, then hour-by-hour through the week (Mon→Sun).
- **Values:** `0` = **cold**, `1` = **night**, `2` = **day**.
- The corresponding temperatures are in `ptemp = [cold, night, day]`.

**Preset temperatures (`ptemp`)**
- Length 3, **[cold, night, day]**.
- Server accepts and often returns temperatures as **strings with one decimal**. Treat as strings when writing to avoid `400` on some backends.

### Write heater settings (partial updates allowed)
**POST `/api/v2/devs/{dev_id}/htr/{addr}/settings`** → 201 (Accepted)

Send only the fields you intend to change (server merges).

Common fields:
- `mode`: `"auto"|"manual"|"off"`
- `stemp`: when setting manual setpoint, send as **string with one decimal**, e.g. `"16.0"`
- `units`: `"C"` or `"F"`
- `ptemp`: array of 3 **strings** with one decimal, e.g. `["10.0","22.0","23.0"]`
- `prog`: array of **168 integers**, each in `{0,1,2}`

**Examples**

Set manual mode with setpoint:
```json
{ "mode": "manual", "stemp": "20.0", "units": "C" }
```

Switch to auto (program) mode:
```json
{ "mode": "auto", "units": "C" }
```

Update preset temperatures (cold, night, day):
```json
{ "ptemp": ["10.0","22.0","23.0"], "units": "C" }
```

Update the full weekly schedule (tri-state grid):
```json
{ "prog": [0,0,0,0,0,0,0, 1,1,2,2,2, ... 168 values ...], "units": "C" }
```

**Notes**
- If you send `stemp` for a manual setpoint, include `mode:"manual"` in the same POST.
- Always include `units` in writes for consistency.
- The server accepts **partial writes**; do not send unrelated fields to avoid clobbering concurrent changes.

---

## Advanced setup (read)
**GET `/api/v2/devs/{dev_id}/htr/{addr}/advanced_setup`** → 200 JSON  
Opaque feature flags (e.g. window mode, true radiant). We currently read-only.

---

## Realtime (Socket.IO 0.9, legacy)
Handshake:
```
GET /socket.io/1/?token=<Bearer>&dev_id=<dev_id>&t=<ms>
→ "<sid>:<hb>:<disc>:websocket,xhr-polling"
```
WebSocket:
```
wss://control.termoweb.net/socket.io/1/websocket/<sid>?token=...&dev_id=...
```
Join namespace:
```
1::/api/v2/socket_io
```
Heartbeat:
- Server sends `2::`; client replies `2::` every ~25–30s.

Snapshot:
```
5::/api/v2/socket_io:{"name":"dev_data","args":[]}
```
Push (batched deltas):
```
5::/api/v2/socket_io:{"name":"data","args":[ [ { "path":"...", "body":{...} }, ... ] ]}
```
Observed paths:
- `/htr/<addr>/settings`
- `/htr/<addr>/advanced_setup`
- `/mgr/nodes`
- `/geo_data`
- `/htr_system/power_limit`

We rely on these events to echo state after writes; a timed fallback refresh is recommended if echo is delayed.

---
