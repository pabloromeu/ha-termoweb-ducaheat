# TermoWeb Cloud API — Confirmed Subset (updated 2025-08-09)

**Sources of truth**
- TermoWeb Android app v2.5.1 (Cordova) decompile, plus
- Live traffic (curl + HA integration).

This document lists **only** endpoints we have verified end-to-end.

## Base
- Host: `https://control.termoweb.net`
- JSON responses; CORS `*` observed.
- Typical headers (not strictly required):  
  `User-Agent: TermoWeb/2.5.1 (Android; HomeAssistant Integration)`  
  `Accept-Language: en-IE,en;q=0.8`  
  `Accept: application/json`

## Auth (Password Grant, public client)
**POST** `/client/token`  
Headers:
- `Authorization: Basic NTIxNzJkY...` *(public client baked into APK v2.5.1)*
- `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`

Form:

username=<email>
password=<password>
grant_type=password

200 JSON → `{ access_token, token_type=Bearer, expires_in, scope }`

Use `Authorization: Bearer <access_token>` for subsequent calls.

## Devices & Nodes
- **GET** `/api/v2/devs/` → 200 `{ devs: [...], invited_to: [] }`
- **GET** `/api/v2/devs/{dev_id}/mgr/nodes` → 200 `{ nodes: [...] }`  
  Heaters are `type: "htr"`.

## Heaters (per node)
### Read
- **GET** `/api/v2/devs/{dev_id}/htr/{addr}/settings` → 200 JSON  
  Representative payload:
  ```json
  {
    "state":"off",
    "mode":"auto",
    "stemp":"10.0",
    "mtemp":"24.2",
    "ptemp":["10.0","22.0","23.0"],
    "units":"C",
    "prog":[ /* 168 ints (0/1/2) */ ],
    "priority":0,
    "name":"Master Bedroom "
  }

mtemp ambient; stemp target; both strings.
prog is 24×7 (168), hourly values 0/1/2 mapping to ptemp[0=cold,1=night,2=day]. Week starts on Monday 00:00.


    POST /api/v2/devs/{dev_id}/htr/{addr}/settings
    JSON body fields (observed):

        mode: "auto" | "manual" | "off"

        stemp: string temperature like "16.0" (server 400s if number in some cases)

        units: "C" (always included)

Rules observed:

    To set a manual setpoint, send both mode:"manual" and stemp:"%.1f".

    Sending stemp as a number (e.g. 16.0) can return 400 {"error_code":5}.

    mode:"auto" and mode:"off" accept with 201 without stemp.

    Treat as non-portable; always send mode:"manual" with setpoint.

Advanced flags

    GET /api/v2/devs/{dev_id}/htr/{addr}/advanced_setup → 200 JSON (window_mode, true_radiant, etc.)

Realtime (Socket.IO 0.9)

Handshake:

    GET /socket.io/1/?token=<Bearer>&dev_id=<dev_id>&t=<ms> → <sid>:<hb>:<disc>:websocket,xhr-polling
    WS:

    wss://control.termoweb.net/socket.io/1/websocket/<sid>?token=...&dev_id=...
    Join:

    1::/api/v2/socket_io
    Heartbeat:

    Server sends 2::; client replies 2:: every ~25–30s.
    Snapshot:

    5::/api/v2/socket_io:{"name":"dev_data","args":[]}
    Push:

    5::/api/v2/socket_io:{"name":"data","args":[ [ { "path":"...", "body":{...} }, ... ] ]}
    Paths: /htr/<addr>/settings, /htr/<addr>/advanced_setup, /mgr/nodes, /geo_data, /htr_system/power_limit.
    