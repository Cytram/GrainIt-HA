"""Constants for the Grainit integration."""

DOMAIN = "grainit"

BASE_URL = "https://portal.grainit.net"
LOGIN_URL = f"{BASE_URL}/?action=login_sql"
MOVEMENTS_URL = f"{BASE_URL}/ajax/dashboard_status.php"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 15  # minutes

# Full history is re-imported into long-term statistics this often.
HISTORY_INTERVAL_HOURS = 6
HISTORY_START = "01-01-2015"

# Fertilizer year ("gødningsår") starts 1 August.
FERTILIZER_YEAR_START_MONTH = 8

RECENT_LOADS = 20

EVENT_NEW_LOAD = "grainit_new_load"
