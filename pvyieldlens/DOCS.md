[English](https://github.com/enecess/ha-pvyieldlens/blob/main/README.md) | [中文](https://github.com/enecess/ha-pvyieldlens/blob/main/README.zh-CN.md) | [Français](https://github.com/enecess/ha-pvyieldlens/blob/main/README.fr.md) | [Deutsch](https://github.com/enecess/ha-pvyieldlens/blob/main/README.de.md) | [Polski](https://github.com/enecess/ha-pvyieldlens/blob/main/README.pl.md) | [Italiano](https://github.com/enecess/ha-pvyieldlens/blob/main/README.it.md)

# PVYieldLens

## Get started

1. Open the Web UI and select **Settings**.
2. Select your Actual power and Irradiance sensors. Select a Module temperature sensor if you have one.
3. In **PV modules**, enter Total max power at STC in W and Temperature coefficient of Pmax in %/°C from your module datasheet.
4. Set the module tilt and direction using a fixed value or a Home Assistant entity for each.
5. Save and open **Dashboard**.

## Views and settings

Use **Dashboard** for current power and today’s generation, **Efficiency** for settled energy and PR comparisons, and **Forecast** for original and corrected weather forecasts. **Settings** stays at the top right, with all three data tabs available. Its directory lists the HA connection, PV modules, Sensors, Forecast and Monitoring settings in that order.

**Monitoring settings** starts collapsed. Select its heading or directory entry to open the controls. Select **?** beside the heading to read the help even while the controls are collapsed. By default, PVYieldLens saves energy and PR for **Efficiency** every 5 minutes, averages the most recent 60 seconds for live values, and recalculates and refreshes those values every 5 seconds. When a sensor exceeds its timeout, the affected period counts as missing and reduces data completeness.

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

Energy is counted only when actual power, irradiance, and measured or estimated module temperature are valid at the same time. Today's energy resets at midnight in your Home Assistant time zone; total energy starts from your first setup.

Choose a language above for the full guide, including settings, output sensors and formulas.

Dashboard retains a fixed ten-minute live trend, reconstructed from stored observations using current monitoring parameters. Missing or timed-out readings remain gaps. Settlement history preserves its original results.

Charts smooth only the drawing. Mouse, touch and keyboard inspection shows original records, including each 15-minute forecast interval. Energy and PR use unsmoothed values. Home time defines calendar dates and forecasts; monitoring and fetch timestamps follow the HA viewer’s server/local preference, or browser time in standalone Docker. UTC offsets distinguish repeated daylight-saving times when needed.

## Generation forecast

Forecast starts automatically when the required settings and Home Assistant location are available. If setup is incomplete, select **Configure PV modules** on the Forecast page. **Settings > Forecast** shows the location name, coordinates and home time zone from the saved connection. Set these values in Home Assistant.

Under **Settings > PV modules**, choose **Fixed value** or **HA entity** independently for tilt and direction. Tilt ranges from 0° to 90° inclusive. Compass azimuth increases clockwise from north (0°) up to but excluding 360°. The fixed direction presets also include east (90°), south (180°), and west (270°). An angle entity must be a `sensor.*`, `number.*`, or `input_number.*` whose state is in degrees (`°`). Use **Refresh entities** in the connection settings to find candidates.

Enter the datasheet NOCT in **PV modules** (above 20°C and at most 80°C, default 45°C). Total max power at STC and the temperature coefficient of Pmax are shared with monitoring. For identical modules, multiply the rating of one module by the module count, for example 500 W × 10 = 5000 W.

For a tracker, every refresh reads the selected HA angles once. All 15-minute periods in that seven-day forecast, including earlier periods today, use that same pair of angles. The Forecast page shows the angles and their read time separately from the weather fetch time. If an entity is unavailable, the page identifies it and shows any still-usable periods from the last forecast. With no usable forecast, energy values show **—** and you can retry the refresh.

Monitoring uses the measured **Module temperature** when you select a sensor. If you leave it blank, PVYieldLens estimates module temperature using Open-Meteo air temperature for your Home Assistant location, your irradiance sensor, and the NOCT set under **PV modules**. Without usable air temperature or irradiance data, estimated module temperature and temperature-dependent power and PR values are unavailable. Forecast uses its own weather inputs and NOCT to calculate **Estimated cell temperature**.

Open-Meteo supplies 15-minute model inputs for today and the next six home calendar days. Some regions or fields interpolate hourly models; a 15-minute output step does not guarantee greater accuracy. Select a date for paired original/corrected energy, power curves and interval details. Today covers the full day; **Remaining today** runs from now to home midnight and decreases between weather fetches. Normal days have 96 intervals, while daylight-saving days can have 92 or 100.

Each date card keeps weather and hourly-forecast high/low temperatures alongside paired energy bars and kWh values. The warm **Today** marker follows home midnight independently of the blue selection. Weather summaries continue to use hourly samples from the same weather request, cache and fetch time. Weather and energy can be unavailable independently; zero remains valid.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching caches survive restart. A failed request keeps the original fetch time, reports the error and retries after 15 minutes. Missing inputs leave affected totals unavailable as **—**.

**Original forecast** is the unchanged weather/NOCT model. **Corrected forecast** multiplies it by recent energy-weighted PR with greater weight on recent completed home dates. In **Settings > Forecast**, **Historical PR days** defaults to n=14 and accepts integers 3–90; the half-life is n/2 days. At least 3 eligible dates with positive estimated energy are required. Actual and estimated energy use the same valid periods after the latest comparable monitoring configuration. A true zero actual yield is eligible, and PR above 100% is retained. Without enough history, corrected values show **—** while original values remain available. Changing n recalculates correction without fetching weather again.

Correction applies to the page and application API only. All 13 HA output IDs and meanings remain unchanged; the four forecast entities continue to report original forecast energy integrated from the 15-minute intervals.

These are estimated DC reference values for one PV module array, using plane-of-array irradiance and a simplified NOCT temperature model. They do not model inverter efficiency/clipping, shading, snow, soiling or system losses and do not guarantee actual AC yield. The four forecast entities are kWh energy values without `state_class`; they can decrease after refresh and are separate from cumulative monitoring energy. They do not provide native HA forecast or Energy dashboard integration.

| Forecast | Entity ID |
| --- | --- |
| Today | `sensor.pvyieldlens_forecast_energy_today` |
| Remaining today | `sensor.pvyieldlens_forecast_energy_remaining_today` |
| Tomorrow | `sensor.pvyieldlens_forecast_energy_tomorrow` |
| Seven days | `sensor.pvyieldlens_forecast_energy_7d` |

### Export a PV power forecast to EMHASS

In **Forecast**, select **Export CSV** for an EMHASS setup where a single inverter carries PV. Choose **Original forecast** or **Corrected forecast**, then select the start date and time in your Home Assistant time zone. Set the optimization interval and number of steps to match the run. The preview shows the window and row count. Each CSV row gives the UTC start time and average PV power in watts for that step.

In EMHASS, set `set_use_pv=true` and `weather_forecast_method=csv`. Save the downloaded `data_weather_forecast.csv` in the `data_path` configured for EMHASS. For each run, export a window starting at its first optimization step, with the same interval and enough rows for the full horizon. The EMHASS v0.18.11 PV reader assigns rows to optimization steps in file order. [EMHASS CSV documentation](https://emhass.readthedocs.io/en/stable/forecasts.html#passing-your-own-forecast-data) · [EMHASS PV reader source](https://github.com/davidusb-geek/emhass/blob/v0.18.11/src/emhass/forecast.py#L1285-L1333)

## Installation and connection

The App requires Home Assistant OS with Home Assistant 2025.9.0 or newer. Install and start PVYieldLens from **Settings > Apps > Install app**, then open its Web UI. Versions before 2026.2 use **Settings > Add-ons > Add-on Store**.

The App connects to Home Assistant automatically. For standalone Docker, enter your Home Assistant address and a long-lived access token belonging to a Home Assistant **administrator** in **Settings**. Administrator access is required to publish the output sensors. The full guides above include Docker installation steps.

## Missing data and backups

After an outage, some periods may remain missing. Keep the app's data when updating or reinstalling. Use Home Assistant backups for the App; for standalone Docker, stop the container before copying the `/data` directory.
