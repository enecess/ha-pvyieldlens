**English** | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Compare your PV modules’ estimated and actual output, follow PR, and see estimated energy for today and in total.

## Features

- Dashboard power, PR and today’s settled generation.
- Efficiency comparisons using original 1, 5 or 10 minute settlements.
- Estimated energy for today and since setup.
- Paired daily energy for 7/30 days or a custom range up to 90 dates.
- Original and corrected 15-minute generation forecasts.
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

Use **Dashboard** for current power and today’s generation, **Efficiency** for settled energy and PR comparisons, and **Forecast** for original and corrected weather forecasts. **Settings** stays at the top right, with all three data tabs available. Its directory covers the HA connection, PV modules, Sensors, Monitoring and Forecast.

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

Save your settings, then open **Dashboard**. The first settled result appears in **Efficiency** when the current period ends. Under **Data timeout**, you can set how long to wait for each sensor before marking its data missing.

Dashboard preloads the last ten minutes of live readings. **Generation data** shows today’s settled estimated/actual power, irradiance and module temperature. Its energy chart defaults to 7 days and also offers 30 days or an inclusive custom range of at most 90 home calendar dates ending no later than today. Missing values stay empty; measured zero stays zero. Historical settlements and cumulative energy are preserved.

Efficiency shows range PR, the change from the comparable previous period in percentage points, and estimated minus actual energy. Today compares with yesterday through the same local clock time; 24 hours compares with the preceding 24 hours; 7/30 days shift the same home calendar range back 7/30 dates. The PR and generation charts share **Daily summary** or **Every {minutes} minutes**, using the configured settlement interval.

Charts smooth only the drawing. Mouse, touch and keyboard inspection shows original records, including each 15-minute forecast interval. Energy and PR use unsmoothed values. Home time defines calendar dates and forecasts; monitoring and fetch timestamps follow the HA viewer’s server/local preference, or browser time in standalone Docker. UTC offsets distinguish repeated daylight-saving times when needed.

## Generation forecast

Forecast is disabled by default on first installation. Enable it under **Settings > Forecast**. Location and time zone come from the saved Home Assistant connection. Set them in HA.

Under **Settings > PV modules**, choose **Fixed value** or **HA entity** independently for tilt and direction. Tilt ranges from 0° to 90° inclusive. Compass azimuth increases clockwise from north (0°) up to but excluding 360°. The fixed direction presets also include east (90°), south (180°), and west (270°). An angle entity must be a `sensor.*`, `number.*`, or `input_number.*` whose state is in degrees (`°`). Use **Refresh entities** in the connection settings to find candidates.

Enter the datasheet NOCT in **PV modules** (above 20°C and at most 80°C, default 45°C). Total max power at STC and the temperature coefficient of Pmax are shared with monitoring. For identical modules, multiply the rating of one module by the module count, for example 500 W × 10 = 5000 W.

For a tracker, every refresh reads the selected HA angles once. All 15-minute periods in that seven-day forecast, including earlier periods today, use that same pair of angles. The Forecast page shows the angles and their read time separately from the weather fetch time. If an entity is unavailable, the page identifies it and shows any still-usable periods from the last forecast. With no usable forecast, energy values show **—** and you can retry the refresh.

Monitoring uses the measured **Module temperature**. Forecast uses **Air temperature** and **Nominal operating cell temperature (NOCT)** to calculate **Estimated cell temperature**. These are separate physical quantities; the monitoring model does not convert module temperature to cell temperature.

Open-Meteo supplies 15-minute model inputs for today and the next six home calendar days. Some regions or fields interpolate hourly models; a 15-minute output step does not guarantee greater accuracy. Select a date for paired original/corrected energy, power curves and interval details. Today covers the full day; **Remaining today** runs from now to home midnight and decreases between weather fetches. Normal days have 96 intervals, while daylight-saving days can have 92 or 100.

Each date card keeps weather and hourly-forecast high/low temperatures alongside paired energy bars and kWh values. The warm **Today** marker follows home midnight independently of the blue selection. Weather summaries continue to use hourly samples from the same weather request, cache and fetch time. Weather and energy can be unavailable independently; zero remains valid.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching caches survive restart. A failed request keeps the original fetch time, reports the error and retries after 15 minutes. Missing inputs leave affected totals unavailable as **—**. The page retains disabled, missing-location, loading and no-data states.

**Original forecast** is the unchanged weather/NOCT model. **Corrected forecast** multiplies it by recent energy-weighted PR with greater weight on recent completed home dates. In **Settings > Forecast**, **Historical PR days** defaults to n=14 and accepts integers 3–90; the half-life is n/2 days. At least 3 eligible dates with positive estimated energy are required. Actual and estimated energy use the same valid periods after the latest comparable monitoring configuration. A true zero actual yield is eligible, and PR above 100% is retained. Without enough history, corrected values show **—** while original values remain available. Changing n recalculates correction without fetching weather again.

Correction applies to the page and application API only. All 13 HA output IDs and meanings remain unchanged; the four forecast entities continue to report original forecast energy integrated from the 15-minute intervals.

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
