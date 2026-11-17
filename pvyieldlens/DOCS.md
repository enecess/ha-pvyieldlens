[English](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.md) | [中文](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.zh-CN.md) | [Français](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.fr.md) | [Deutsch](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.de.md) | [Polski](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.pl.md) | [Italiano](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.it.md)

# PVYieldLens

## Get started

1. Open the Web UI and select **Settings**.
2. Select your Actual power, Module temperature and Irradiance sensors.
3. Enter Total max power at STC in W and Temperature coefficient of Pmax in %/°C from your module datasheet.
4. Save and open **Live**.

## Views and settings

Use **Live** for current averages and sensor diagnostics, **History** for settled periods and the selected range's energy/PR, and **Forecast** for weather-based generation estimates. The History page shows actual energy, estimated energy, PR and data completeness for the selected range. The separate gear-and-text **Settings** entry sits at the top right while all three data tabs remain available. Its category directory scrolls one continuous form: Home Assistant connection, PV modules, Sensors, Monitoring and Forecast.

**Save configuration** keeps Settings open. **Discard changes** reloads the saved configuration from the server and replaces edits; a failed reload retains your draft for retry. Leaving with unsaved changes asks you to keep editing or discard them. Reentering Settings loads the saved configuration again.

**Theme mode** offers Auto, Light and Dark. Auto follows Home Assistant's Theme mode inside its interface and falls back to the system preference outside a usable HA context. Light and Dark are local overrides; Auto resumes following the host. Language and theme changes preserve the settings draft. All frontend assets are served locally.

## History ranges and daily results

History opens on **Today**, from midnight in the Home Assistant household time zone to now. **24 hours** is a rolling range of complete settlements. **7 days** and **30 days** are household calendar dates including today, with 7 or 30 fixed date slots; daylight-saving dates can have 23 or 25 hours. The selected range survives navigation between views.

The four cards show actual energy first, estimated energy, energy-weighted PR and data completeness. The settled start and end below the cards show the data actually included. The 7/30-day views add separate daily energy bars and daily PR above the retained power and PR detail charts. Hover, touch or use arrow keys to inspect a date, including a measured zero. Missing dates remain empty; PR is unavailable when estimated energy is zero. Today is marked with the latest included settlement time in household time. Ordinary partial coverage retains known energy and shows its data completeness.

Exact cross-midnight settlements can contribute a boundary fragment; its tooltip shows both the included span and the original settlement. Records from a different household time zone or without retained allocation detail may lack an exact daily allocation. Such an outer boundary is excluded and flagged. At an internal midnight, the original settlement remains in range cards and details, while the affected daily values are unavailable. No daily values are guessed from duration.

Cumulative estimated energy remains available through `sensor.pvyieldlens_estimated_energy_today` and `sensor.pvyieldlens_estimated_energy_lifetime`, independently of the selected History range.

## Updates

- History: 1, 5 or 10 minutes; 5 minutes by default.
- Live average: the latest 60 seconds by default.
- Refresh: every 5 seconds by default.

Use the language menu at the top right to change the page language.

## Results

Performance ratio (PR) compares actual power with estimated power. The optimizable power is estimated power minus actual power. PR may be above 100%, and the optimizable power may be negative. PR is not shown when estimated power is zero.

Energy is counted only when all three sensors have data. Today's energy resets at midnight in your Home Assistant time zone; total energy starts from your first setup.

Choose a language above for the full guide, including settings, output sensors and formulas.

Live preloads a fixed rolling ten minutes when opened or reconnected. Each point still uses **Average over**, and collection follows **Update every**. This recent trend is reconstructed from stored observations using the current monitoring parameters; it is not a log of previously published snapshots. Missing or timed-out observations and the current offline endpoint remain gaps. Earlier connection outages without an identifiable observation gap cannot be reconstructed precisely. History keeps the original settled results. While diagnostics are expanded on a visible Live page, the three configured sensors are read from Home Assistant about once a second. Closing diagnostics, switching pages or hiding the browser tab pauses these requests. Ages use Home Assistant time and advance locally between reads; the monitoring interval and chart updates are unchanged.

Charts use smooth paths for display only. Pointer, touch and keyboard tooltips show original sample values; Forecast tooltips show the original hourly interval. Energy and PR use the original data. Household time controls daily totals, Forecast dates, weather, Today and hourly periods. Live/History timestamps and update/fetch times follow the HA viewer's server/local time preference; standalone Docker uses browser time. Unreadable HA preferences fall back to household time. A short note appears when these time zones differ; UTC offsets appear only to distinguish repeated daylight-saving times or a period spanning an offset change.

## Generation forecast

Forecast is disabled by default on first installation. Under **Settings > Forecast**, enable it, enter module tilt (0–90°), compass direction (north 0°, east 90°, south 180°, west 270°, or a custom value from 0° to below 360°), and NOCT from the datasheet (above 20°C, at most 80°C; default 45°C). Total max power at STC and Temperature coefficient of Pmax are shared with monitoring. Location and time zone come automatically from the saved Home Assistant connection; change them in HA.

Monitoring uses the measured **Module temperature**. Forecast uses **Air temperature** and **Nominal operating cell temperature (NOCT)** to calculate **Estimated cell temperature**. These are separate physical quantities; the monitoring model does not convert module temperature to cell temperature.

Open-Meteo supplies hourly weather for today and the following six local calendar days. Select a date for full-day energy, the hourly power curve and numeric interval details. Today's forecast includes all of today, while **Remaining today** counts only from now to local midnight. Both use the latest successful weather fetch and are separate from settled estimated energy calculated from sensor readings. Remaining energy decreases as time passes between fetches; a new forecast can also revise the full-day estimate.

Each date card shows weather, hourly-forecast high/low air temperatures, its energy bar and kWh. The warm **Today** label follows household midnight and remains visible when a different date is selected in blue. Daily temperatures use raw hourly samples, and representative weather uses the day's maximum known WMO code. Each field requires every expected UTC hourly sample inside that household day, including 23/25-hour days and fractional time zones; an incomplete field is unavailable while a complete companion field stays visible. Zero values remain valid. Unknown weather uses a neutral icon. Weather uses the same hourly request, cache and fetch time as power, with no additional refresh cadence.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching cached data survives restart. A failed refresh retains its original fetch time and shows stale data; retries occur after 15 minutes. Data at least two hours old is also stale. Missing weather intervals make affected totals unavailable, with data completeness shown separately; missing data is never assumed to be zero. Disabled, missing HA location, initial loading and unavailable states are shown explicitly.

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
