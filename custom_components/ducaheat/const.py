from __future__ import annotations

DOMAIN = "ducaheat"

# Polling defaults (seconds)
DEFAULT_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 600

# Config keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_BASE_URL = "base_url"
CONF_BASIC_B64 = "basic_b64"
CONF_POLL_INTERVAL = "poll_interval"

# (kept for possible future manual IDs, not used by v2 flow)
CONF_HOME_ID = "home_id"
CONF_NODE_IDS = "node_ids"

# Options
CONF_BOOST_MINUTES = "boost_minutes"
DEFAULT_BOOST_MINUTES = 120  # used when setting temperature

# Ducaheat tenant defaults (matches your curl)
DEFAULT_BASE_URL = "https://api-tevolve.termoweb.net"
DUCAHEAT_BASIC_AUTH_B64 = "NWM0OWRjZTk3NzUxMDM1MTUwNmM0MmRiOnRldm9sdmU="

# Headers
USER_AGENT = "HomeAssistant Ducaheat/0.3"
ACCEPT_LANGUAGE = "en-US"