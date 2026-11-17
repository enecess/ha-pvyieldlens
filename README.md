**English** | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Compare your PV modules’ estimated and actual output, follow PR, and see estimated energy for today and in total.

## Features

- Live power, PR and optimizable power.
- Power and PR history at 1, 5 or 10 minute intervals.
- Estimated energy for today and since setup.
- Charts for the last 24 hours, 7 days or 30 days.
- Six languages, with a language menu at the top right.

## Quick start

### Home Assistant App

For Home Assistant OS.

[![Add the PVYieldLens App repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Click the button above and confirm **Add** in Home Assistant.
2. Find **PVYieldLens** in the App store, then install and start it.
3. Open the Web UI and go to **Settings** to choose your sensors and enter your PV module details.

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

Use **Live** for current sensor averages and diagnostics, **History** for settled periods and the selected range's energy/PR, and **Forecast** for weather-based generation estimates. The separate gear-and-text **Settings** entry is at the top right; all three data tabs remain available. Its category directory scrolls one continuous form: Home Assistant connection, PV modules, Sensors, Monitoring, and Forecast.

**Save configuration** keeps you in Settings. **Discard changes** reloads the saved configuration from the server and replaces your edits; if loading fails, your draft remains available to retry. Leaving with unsaved changes asks you to keep editing or discard them. Returning to Settings loads the saved configuration again.

The top-right **Theme mode** menu offers Auto, Light and Dark. Auto follows Home Assistant's Theme mode inside its Web UI and uses the system preference outside a usable Home Assistant context. Light or Dark overrides Auto locally; selecting Auto resumes following the host. Language and theme changes preserve your settings draft.

| Setting | What to enter |
| --- | --- |
| Total max power at STC | Sum of module maximum powers under standard test conditions (STC), in W, e.g. `5000`. |
| Temperature coefficient of Pmax | The Pmax coefficient from the module datasheet, in %/°C, e.g. `-0.35`. |
| Actual power | Your solar generation power sensor (W or kW). |
| Module temperature | Your module temperature sensor (°C, °F or K). |
| Irradiance | An irradiance sensor in the same plane as the modules (W/m² or kW/m²). |
| Settlement interval | 1, 5 or 10 minutes. Default: 5 minutes. |
| Average over | Time used to average live readings. Default: 60 seconds. |
| Update every | How often live results refresh. Default: 5 seconds. |

Save your settings, then open **Live**. The first settled result appears in **History** when the current period ends. Under **Data timeout**, you can set how long to wait for each sensor before marking its data missing.

Live preloads a fixed rolling ten minutes when opened or reconnected. Each point still uses **Average over**, and collection follows **Update every**. This recent trend is reconstructed from stored observations using the current monitoring parameters; it is not a log of previously published snapshots. Missing or timed-out observations and the current offline endpoint remain gaps. Earlier connection outages without an identifiable observation gap cannot be reconstructed precisely. History keeps the original settled results. Source diagnostic ages advance every second locally without extra sensor requests.

Charts use smooth paths for display only. Pointer, touch and keyboard tooltips show original sample values; Forecast tooltips show the original hourly interval. Energy and PR use the original data. Household time controls daily totals, Forecast dates, weather, Today and hourly periods. Live/History timestamps and update/fetch times follow the HA viewer's server/local time preference; standalone Docker uses browser time. Unreadable HA preferences fall back to household time. A short note appears when these time zones differ; UTC offsets appear only to distinguish repeated daylight-saving times or a period spanning an offset change.

## Generation forecast

Forecast is disabled by default on first installation. Under **Settings > Forecast**, enable it, enter module tilt (0–90°), compass direction (north 0°, east 90°, south 180°, west 270°, or a custom value from 0° to below 360°), and NOCT from the datasheet (above 20°C, at most 80°C; default 45°C). Total max power at STC and Temperature coefficient of Pmax are shared with monitoring. Location and time zone come automatically from the saved Home Assistant connection; change them in HA.

Monitoring uses the measured **Module temperature**. Forecast uses **Air temperature** and **Nominal operating cell temperature (NOCT)** to calculate **Estimated cell temperature**. These are separate physical quantities; the monitoring model does not convert module temperature to cell temperature.

Open-Meteo supplies hourly weather for today and the following six local calendar days. Select a date for full-day energy, the hourly power curve and numeric interval details. Today's forecast includes all of today, while **Remaining today** counts only from now to local midnight. Both use the latest successful weather fetch and are separate from settled estimated energy calculated from sensor readings. Remaining energy decreases as time passes between fetches; a new forecast can also revise the full-day estimate.

Each date card shows weather, hourly-forecast high/low air temperatures, its energy bar and kWh. The warm **Today** label follows household midnight and remains visible when a different date is selected in blue. Daily temperatures use raw hourly samples, and representative weather uses the day's maximum known WMO code. Each field requires every expected UTC hourly sample inside that household day, including 23/25-hour days and fractional time zones; an incomplete field is unavailable while a complete companion field stays visible. Zero values remain valid. Unknown weather uses a neutral icon. Weather uses the same hourly request, cache and fetch time as power, with no additional refresh cadence.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching cached data survives restart. A failed refresh retains its original fetch time and shows stale data; retries occur after 15 minutes. Data at least two hours old is also stale. Missing weather intervals make affected totals unavailable, with data completeness shown separately; missing data is never assumed to be zero. Disabled, missing HA location, initial loading and unavailable states are shown explicitly.

These are estimated DC reference values for one PV module array, using plane-of-array irradiance and a simplified NOCT temperature model. They do not model inverter efficiency/clipping, shading, snow, soiling or system losses and do not guarantee actual AC yield. The four forecast entities are kWh energy values without `state_class`; they can decrease after refresh and are separate from cumulative monitoring energy. They do not provide native HA forecast or Energy dashboard integration.

## Output sensors

| Metric | HA entity name | Unit |
| --- | --- | --- |
| Settled estimated power | `settled_estimated_power` | W |
| Settled actual power | `settled_actual_power` | W |
| Settled PR | `settled_pr` | % |
| Estimated energy today | `estimated_energy_today` | kWh |
| Lifetime estimated energy | `estimated_energy_lifetime` | kWh |
| Live estimated power | `live_estimated_power` | W |
| Live actual power | `live_actual_power` | W |
| Live PR | `live_pr` | % |
| Live optimizable power | `live_optimizable_power` | W |
| Forecast energy today | `forecast_energy_today` | kWh |
| Forecast energy remaining today | `forecast_energy_remaining_today` | kWh |
| Forecast energy tomorrow | `forecast_energy_tomorrow` | kWh |
| Forecast energy for 7 days | `forecast_energy_7d` | kWh |

The HA entity name is its display name. The full entity ID is `sensor.pvyieldlens_<HA entity name>`; for example, `sensor.pvyieldlens_settled_estimated_power`.

## PR formula

Estimated power takes Total max power at STC, module temperature and irradiance into account:

```text
P_estimated = P_stc × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_estimated × 100%
```

`P_stc`: Total max power at STC (W); `K`: Temperature coefficient of Pmax (%/°C), entered as the datasheet percentage, e.g. `-0.35`; `T`: Module temperature (°C); `G`: Irradiance in the module plane (W/m²). The app divides K by 100 once.

Performance ratio (PR) compares actual power with estimated power. Optimizable power is estimated power minus actual power and can be negative.

## Reading the results

- PR can be above 100%. When estimated power is zero, PR is not shown.
- A negative optimizable power means actual power is higher than estimated.
- Energy is counted only while all three sensors have data. Missing periods are left out.
- Today’s energy resets at midnight in your Home Assistant time zone. Total energy starts from your first setup.

After an outage, some periods may remain missing. Keep the app's data when updating or reinstalling. Use Home Assistant backups for the App; for standalone Docker, stop the container before copying the `/data` directory.
