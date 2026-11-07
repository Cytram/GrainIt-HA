# Grainit for Home Assistant (v0.2)

Custom integration that reads registered loads (slurry/biomass movements) from the Grainit portal and shows them in Home Assistant: today, this week, this month and this fertilizer year, the latest load, the last 20 loads, and the full history in graphs.

Grainit has no public API. The integration logs in the same way the website does and reads the same data as the "Bevægelser/log" page.

## Installation

1. Copy `custom_components/grainit` to `<HA config>/custom_components/grainit` (replace the old version if you have one).
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → "Grainit", and enter your Grainit email and password.
4. Optional: set up the dashboard in `dashboard/grainit_dashboard.yaml` and the notification in `dashboard/grainit_notifikation.yaml` (instructions are at the top of each file).

Upgrading from v0.1: delete the old Grainit entry under Devices & services first, then restart and add it again. The old "24 timer" sensors disappear.

## Sensors

Per product and direction, e.g. `raagylle_kvaeg_ud`, `afgasset_gylle_ind`, `dybstroeelse_ud`:

| Entity | Meaning |
|---|---|
| `sensor.grainit_<key>_i_dag` | tonnes today |
| `sensor.grainit_<key>_denne_uge` | tonnes this week (Monday–Sunday) |
| `sensor.grainit_<key>_denne_maaned` | tonnes this month |
| `sensor.grainit_<key>_goedningsaar` | tonnes since 1 August |
| `sensor.grainit_<key>_laes_i_dag` | loads today |
| `sensor.grainit_<key>_seneste` | time of the latest load |

Overall:

| Entity | Meaning |
|---|---|
| `sensor.grainit_seneste_laes` | time of the latest load. Attributes: product, tonnes, from, to, driver, and `laes` = the last 20 loads |
| `sensor.grainit_laes_i_dag` | loads today |
| `sensor.grainit_laes_denne_maaned` | loads this month |

New products show up automatically.

## Graphs with full history

On start and every 6 hours, the whole history is imported into Home Assistant's long-term statistics as `grainit:<key>` (cumulative tonnes per hour). A statistics-graph card with `stat_types: [change]` and `period: day/week/month` then shows tonnes per period, including everything from before the integration was installed.

## Event for new loads

Every new load fires the event `grainit_new_load` with `product`, `direction`, `tonnes`, `kg`, `driver`, `from`, `to`, `time` and `registration_id`. It can be used for notifications (see `grainit_notifikation.yaml`).

## How it talks to Grainit

- Login: `POST https://portal.grainit.net/?action=login_sql` (form: `offset`, `email`, `password`, `remember_login`). The session is kept in its own cookie jar.
- Loads: `GET https://portal.grainit.net/ajax/dashboard_status.php?action=get_movements_status_details_v2&start_date=DD-MM-YYYY&end_date=DD-MM-YYYY&…` returns `{"success":1,"html":"<table>…"}` with one row per load.
- If the portal answers "Ingen adgang" or something that isn't JSON, it logs in again and retries once. If it still fails, the sensors keep their last values until the next update.
- Update interval: 15 minutes by default, changeable in the integration's options.

## Files

- `api.py` – login, fetching and parsing the load table
- `summary.py` – totals per day/week/month/fertilizer year (no HA dependencies)
- `statistics.py` – import into long-term statistics
- `__init__.py` – setup, coordinator, events
- `sensor.py` – the sensors
- `config_flow.py` – setup, reauth and options

## Tests

```bash
python3 tests/test_grainit.py
```

Runs without Home Assistant or aiohttp installed.
