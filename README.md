**English** | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Compare your solar panels’ expected and actual output, follow PR, and see expected energy for today and in total.

## Features

- Live power, PR and power gap.
- Power and PR history at 1, 5 or 10 minute intervals.
- Expected energy for today and since setup.
- Charts for the last 24 hours, 7 days or 30 days.
- Six languages, with a language menu at the top right.

## Quick start

### Home Assistant App

For Home Assistant OS.

[![Add the PVYieldLens App repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Click the button above and confirm **Add** in Home Assistant.
2. Find **PVYieldLens** in the App store, then install and start it.
3. Open the Web UI and go to **Settings** to choose your sensors and enter your panel details.

If the button does not open Home Assistant, go to **Settings > Apps > Install app > top-right menu > Repositories** and add:

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

On Home Assistant versions before 2026.2, use **Settings > Add-ons > Add-on Store > top-right menu > Repositories**. The App requires Home Assistant 2025.9.0 or newer.

### Docker

Download this repository and open its folder. Create your settings file:

```sh
cp .env.example .env
```

Set `PVYL_WEB_PASSWORD` in `.env` to your chosen password, then start the app:

```sh
docker compose up -d --build
```

Open [localhost:8099](http://localhost:8099). Sign in as `admin` with the password you set. For the first connection, enter your Home Assistant address and a long-lived access token belonging to a Home Assistant **administrator** in **Settings**, then select **Refresh sensors**. When a URL and token are already configured, sensors load automatically the first time you enter **Settings**. Use **Refresh sensors** after changing the connection, to refresh the list or to retry a failed request. Administrator access is required to publish the output sensors.

The default address works on the Docker host. To open the page from another device, change `127.0.0.1:8099:8099` to `8099:8099` in `compose.yaml`.

## Settings

Use **Live** for current sensor averages and diagnostics, **History** for settled periods and the selected range's energy/PR, and **Forecast** for weather-based generation estimates. History's today/lifetime totals remain separate from its selected range. The separate gear-and-text **Settings** entry is at the top right; all three data tabs remain available. Its category directory scrolls one continuous form: Home Assistant connection, Solar panels, Sensors, Monitoring, and Forecast.

**Save** keeps you in Settings. **Cancel** reloads the saved configuration from the server and replaces your edits; if loading fails, your draft remains available to retry. Leaving with unsaved changes asks you to keep editing or discard them. Returning to Settings loads the saved configuration again.

The top-right **Theme mode** menu offers Auto, Light and Dark. Auto follows Home Assistant's Theme mode inside its Web UI and uses the system preference outside a usable Home Assistant context. Light or Dark overrides Auto locally; selecting Auto resumes following the host. Language and theme changes preserve your settings draft.

| Setting | What to enter |
| --- | --- |
| Total rated power | Total panel power in W, e.g. `5000`. |
| Temperature coefficient K | The value from the panel datasheet, in %/°C, e.g. `-0.35`. |
| Actual Power | Your solar generation power sensor (W or kW). |
| Module Temperature | Your panel temperature sensor (°C, °F or K). |
| Irradiance | A sunlight sensor in the same plane as the panels (W/m² or kW/m²). |
| History interval | 1, 5 or 10 minutes. Default: 5 minutes. |
| Average over | Time used to average live readings. Default: 60 seconds. |
| Update every | How often live results refresh. Default: 5 seconds. |

Save your settings, then open **Live**. The first settled result appears in **History** when the current period ends. Under **Data timeout**, you can set how long to wait for each sensor before marking its data missing.

## Generation forecast

Forecast is disabled by default, including after an upgrade. Under **Settings > Forecast**, enable it, enter panel tilt (0–90°), compass direction (north 0°, east 90°, south 180°, west 270°, or a custom value from 0° to below 360°), and NOCT from the datasheet (above 20°C, at most 80°C; default 45°C). Rated power and K are shared with monitoring. Location and time zone come automatically from the saved Home Assistant connection; change them in HA.

Open-Meteo supplies hourly weather for today and the following six local calendar days. Select a date for full-day energy, the hourly power curve and numeric interval details; timestamps include UTC offsets. Today's forecast includes all of today, while **Remaining today** counts only from now to local midnight. Both use the latest successful weather fetch and are separate from settled theoretical energy calculated from sensor readings. Remaining energy decreases as time passes between fetches; a new forecast can also revise the full-day estimate.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching cached data survives restart. A failed refresh retains its original fetch time and shows stale data; retries occur after 15 minutes. Data at least two hours old is also stale. Missing weather intervals make affected totals unavailable, with completeness shown separately; missing data is never assumed to be zero. Disabled, missing HA location, initial loading and unavailable states are shown explicitly.

These are theoretical DC reference values for one panel array, using plane-of-array irradiance and a simplified NOCT temperature model. They do not model inverter efficiency/clipping, shading, snow, soiling or system losses and do not guarantee actual AC yield. The four forecast entities are kWh energy values without `state_class`; they can decrease after refresh and are separate from cumulative monitoring energy. They do not provide native HA forecast or Energy dashboard integration.

## Output sensors

| Result | Entity ID | Unit |
| --- | --- | --- |
| Expected power | `sensor.pvyieldlens_estimated_power` | W |
| Actual power | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| Expected energy today | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| Total expected energy | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| Live expected power | `sensor.pvyieldlens_realtime_estimated_power` | W |
| Live actual power | `sensor.pvyieldlens_realtime_actual_power` | W |
| Live PR | `sensor.pvyieldlens_realtime_pr` | % |
| Live power gap | `sensor.pvyieldlens_realtime_optimizable_power` | W |
| Forecast today | `sensor.pvyieldlens_forecast_energy_today` | kWh |
| Forecast remaining today | `sensor.pvyieldlens_forecast_energy_remaining_today` | kWh |
| Forecast tomorrow | `sensor.pvyieldlens_forecast_energy_tomorrow` | kWh |
| Forecast for 7 days | `sensor.pvyieldlens_forecast_energy_7d` | kWh |

## PR formula

Expected power takes panel size, temperature and sunlight into account:

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated`: rated power (W); `K`: temperature coefficient (%/°C); `T`: panel temperature (°C); `G`: sunlight on the panels (W/m²).

PR compares actual power with expected power. The power gap is expected power minus actual power.

## Reading the results

- PR can be above 100%. When expected power is zero, PR is not shown.
- A negative power gap means actual power is higher than expected.
- Energy is counted only while all three sensors have data. Missing periods are left out.
- Today’s energy resets at midnight in your Home Assistant time zone. Total energy starts from your first setup.

After an outage, some periods may remain missing. Keep the app's data when updating or reinstalling. Use Home Assistant backups for the App; for standalone Docker, stop the container before copying the `/data` directory.
