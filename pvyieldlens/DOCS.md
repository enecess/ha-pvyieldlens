[English](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.md) | [中文](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.zh-CN.md) | [Français](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.fr.md) | [Deutsch](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.de.md) | [Polski](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.pl.md) | [Italiano](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.it.md)

# PVYieldLens

## Get started

1. Open the Web UI and select **Settings**.
2. Select your Actual power, Module temperature and Irradiance sensors.
3. Enter Total max power at STC in W and Temperature coefficient of Pmax in %/°C from your module datasheet.
4. Save and open **Dashboard**.

## Views and settings

Use **Dashboard** for current power and today’s generation, **Efficiency** for settled energy and PR comparisons, and **Forecast** for original and corrected weather forecasts. **Settings** stays at the top right, with all three data tabs available. Its directory covers the HA connection, PV modules, Sensors, Monitoring and Forecast.

**Save configuration** keeps Settings open. **Discard changes** reloads the saved configuration from the server and replaces edits; a failed reload retains your draft for retry. Leaving with unsaved changes asks you to keep editing or discard them. Reentering Settings loads the saved configuration again.

**Theme mode** offers Auto, Light and Dark. Auto follows Home Assistant's Theme mode inside its interface and falls back to the system preference outside a usable HA context. Light and Dark are local overrides; Auto resumes following the host. Language and theme changes preserve the settings draft. All frontend assets are served locally.

## Generation and efficiency

Dashboard preloads the last ten minutes of live readings. **Generation data** shows today’s settled estimated/actual power, irradiance and module temperature. Its energy chart defaults to 7 days and also offers 30 days or an inclusive custom range of at most 90 home calendar dates ending no later than today. Missing values stay empty; measured zero stays zero. Historical settlements and cumulative energy are preserved.

Efficiency shows range PR, the change from the comparable previous period in percentage points, and estimated minus actual energy. Today compares with yesterday through the same local clock time; 24 hours compares with the preceding 24 hours; 7/30 days shift the same home calendar range back 7/30 dates. The PR and generation charts share **Daily summary** or **Every {minutes} minutes**, using the configured settlement interval.

Range PR divides actual energy by estimated energy from the same valid periods. Missing dates remain empty and measured zero stays zero. Exact saved cross-midnight allocations contribute without rewriting original settlements or cumulative energy; unavailable allocations are not guessed by duration.

Cumulative estimated energy remains available through `sensor.pvyieldlens_estimated_energy_today` and `sensor.pvyieldlens_estimated_energy_lifetime`, independently of the selected Efficiency range.

## Updates

- Settlement: 1, 5 or 10 minutes; 5 minutes by default.
- Live average: the latest 60 seconds by default.
- Refresh: every 5 seconds by default.

Use the language menu at the top right to change the page language.

## Results

Performance ratio (PR) compares actual power with estimated power. The optimizable power is estimated power minus actual power. PR may be above 100%, and the optimizable power may be negative. PR is not shown when estimated power is zero.

Energy is counted only when all three sensors have data. Today's energy resets at midnight in your Home Assistant time zone; total energy starts from your first setup.

Choose a language above for the full guide, including settings, output sensors and formulas.

Dashboard retains a fixed ten-minute live trend, reconstructed from stored observations using current monitoring parameters. Missing or timed-out readings remain gaps. Settlement history preserves its original results.

Charts smooth only the drawing. Mouse, touch and keyboard inspection shows original records, including each 15-minute forecast interval. Energy and PR use unsmoothed values. Home time defines calendar dates and forecasts; monitoring and fetch timestamps follow the HA viewer’s server/local preference, or browser time in standalone Docker. UTC offsets distinguish repeated daylight-saving times when needed.

## Generation forecast

Forecast is disabled by default on first installation. Under **Settings > Forecast**, enable it, enter module tilt (0–90°), compass direction (north 0°, east 90°, south 180°, west 270°, or a custom value from 0° to below 360°), and NOCT from the datasheet (above 20°C, at most 80°C; default 45°C). Total max power at STC and Temperature coefficient of Pmax are shared with monitoring. Location and time zone come automatically from the saved Home Assistant connection; change them in HA.

Monitoring uses the measured **Module temperature**. Forecast uses **Air temperature** and **Nominal operating cell temperature (NOCT)** to calculate **Estimated cell temperature**. These are separate physical quantities; the monitoring model does not convert module temperature to cell temperature.

Open-Meteo supplies 15-minute model inputs for today and the next six home calendar days. Some regions or fields interpolate hourly models; a 15-minute output step does not guarantee greater accuracy. Select a date for paired original/corrected energy, power curves and interval details. Today covers the full day; **Remaining today** runs from now to home midnight and decreases between weather fetches. Normal days have 96 intervals, while daylight-saving days can have 92 or 100.

Each date card keeps weather and hourly-forecast high/low temperatures alongside paired energy bars and kWh values. The warm **Today** marker follows home midnight independently of the blue selection. Weather summaries continue to use hourly samples from the same weather request, cache and fetch time. Weather and energy can be unavailable independently; zero remains valid.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching caches survive restart. A failed request keeps the original fetch time, reports the error and retries after 15 minutes. Missing inputs leave affected totals unavailable as **—**. The page retains disabled, missing-location, loading and no-data states.

**Original forecast** is the unchanged weather/NOCT model. **Corrected forecast** multiplies it by recent energy-weighted PR with greater weight on recent completed home dates. In **Settings > Forecast**, **Historical PR days** defaults to n=14 and accepts integers 3–90; the half-life is n/2 days. At least 3 eligible dates with positive estimated energy are required. Actual and estimated energy use the same valid periods after the latest comparable monitoring configuration. A true zero actual yield is eligible, and PR above 100% is retained. Without enough history, corrected values show **—** while original values remain available. Changing n recalculates correction without fetching weather again.

Correction applies to the page and application API only. All 13 HA output IDs and meanings remain unchanged; the four forecast entities continue to report original forecast energy integrated from the 15-minute intervals.

These are estimated DC reference values for one PV module array, using plane-of-array irradiance and a simplified NOCT temperature model. They do not model inverter efficiency/clipping, shading, snow, soiling or system losses and do not guarantee actual AC yield. The four forecast entities are kWh energy values without `state_class`; they can decrease after refresh and are separate from cumulative monitoring energy. They do not provide native HA forecast or Energy dashboard integration.

| Forecast | Entity ID |
| --- | --- |
| Today | `sensor.pvyieldlens_forecast_energy_today` |
| Remaining today | `sensor.pvyieldlens_forecast_energy_remaining_today` |
| Tomorrow | `sensor.pvyieldlens_forecast_energy_tomorrow` |
| Seven days | `sensor.pvyieldlens_forecast_energy_7d` |

## Installation and connection

The App requires Home Assistant OS with Home Assistant 2025.9.0 or newer. Install and start PVYieldLens from **Settings > Apps > Install app**, then open its Web UI. Versions before 2026.2 use **Settings > Add-ons > Add-on Store**.

The App connects to Home Assistant automatically. For standalone Docker, enter your Home Assistant address and a long-lived access token belonging to a Home Assistant **administrator** in **Settings**. Administrator access is required to publish the output sensors. The full guides above include Docker installation steps.

## Missing data and backups

After an outage, some periods may remain missing. Keep the app's data when updating or reinstalling. Use Home Assistant backups for the App; for standalone Docker, stop the container before copying the `/data` directory.
