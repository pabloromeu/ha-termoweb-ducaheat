# Ducaheat heaters for Home Assistant

Control your **Ducaheat** electric heaters in **Home Assistant** — from the HA app, automations, scenes, and voice assistants.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-termoweb&repository=ha-termoweb&category=integration)
[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=termoweb)

> You must install the integration first (via HACS or manual copy) before the “Add integration” button will work.

---

## Who is this for?

For someone who runs Home Assistant and already uses the **Ducaheat** mobile app or signs in at the **Ducaheat/TermoWeb hybrid API endpoint** to manage their electric heaters. They want to see and control those heaters in Home Assistant, use automations (e.g., bedtime setback), and enable voice control. The manufacturer’s app doesn’t integrate with HA — this add-on provides the missing link.

---

## About this integration

This integration is designed specifically for **Ducaheat** systems.

---

## What you can do in Home Assistant

- Change mode: **On**, **Off**, **Auto**, or **Boost**.  
- View current temperature and heating state.  
- Use **automations**, **scenes**, and **voice assistants** (via HA’s Google/Alexa integrations).  
- Note: Target temperature changes are only possible via **Boost** mode.

---

## What you’ll need

- A working Ducaheat setup (gateway connected to the router, heaters paired).  
- The **Ducaheat account email & password** (the same used in the mobile app / web).  
- Home Assistant (Core, OS, or Container) with internet access.

---

## Install (simple, step-by-step)

### Option A — HACS (recommended)

1) Open **HACS → Integrations** in Home Assistant.  
2) Click **⋮** (top-right) → **Custom repositories** → **Add**.  
3) Paste: `https://github.com/pabloromeu/ha-termoweb-ducaheat` and choose **Integration**.  
   Or click:  
   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-termoweb&repository=ha-termoweb&category=integration)  
4) Search for **Ducaheat** in HACS and **Install**.  
5) **Restart Home Assistant** when prompted.

### Option B — Manual

1) Download this repository.  
2) Copy the folder **`custom_components/termoweb`** to **`<config>/custom_components/termoweb`** on the HA system.  
3) **Restart Home Assistant**.

---

## Set up the integration

1) In Home Assistant go to **Settings → Devices & Services → Add Integration** and search **Ducaheat**,  
   or click:  
   [![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=termoweb)  
2) Enter the **Ducaheat login** (email & password).  
3) **Portal address**:  
   - Enter the appropriate Ducaheat/TermoWeb hybrid API endpoint used today.  
4) Complete the wizard. Heaters will appear under **Devices**; add them to dashboards or use them in automations.

---

## Tips
- **Voice control:** Expose heater entities via Home Assistant’s Google or Alexa integrations.  
- **Automations idea:** Lower temperature when nobody’s home; switch to **Off** if a window sensor is open for 10+ minutes.

---

## Troubleshooting

- **Login fails:** First confirm credentials at the Ducaheat control app or portal.  
- **No devices found:** Check the **gateway** is powered and online (LEDs), and that the manufacturer app shows heaters online.  
- **Settings limitations:** Not all heater settings may be adjustable due to API limitations.  
- **Need help?** Open a GitHub issue with brand/model and a brief description. **Never share passwords or private info.**

---

## Privacy & Security

- Credentials stay in Home Assistant.  
- Access tokens are **redacted** from logs.  
- This project is **not affiliated** with S&P, ATC, Ecotermi/Linea Plus, EHC, or TermoWeb.

---

## Search keywords

*Home Assistant Ducaheat, Ducaheat heaters Home Assistant, Ducaheat control app, Ducaheat integration Home Assistant*
