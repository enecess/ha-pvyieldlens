[English](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.md) | [中文](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.zh-CN.md) | [Français](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.fr.md) | [Deutsch](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.de.md) | [Polski](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.pl.md) | [Italiano](https://github.com/enecess/ha-pvyieldlens/blob/dev_v0/README.it.md)

# PVYieldLens

## Get started

1. Open the Web UI and select **Settings**.
2. Select your solar power, panel temperature and sunlight sensors.
3. Enter the total rated power in W and temperature coefficient K in %/°C from your panel datasheet.
4. Save and open **Live**.

## Views and settings

Use **Live** for current averages and sensor diagnostics, **History** for settled periods and the selected range's energy/PR, and **Forecast** for weather-based generation estimates. Today's settled and lifetime totals remain separate from the history range. The separate gear-and-text **Settings** entry sits at the top right while all three data tabs remain available. Its category directory scrolls one continuous form: Home Assistant connection, Solar panels, Sensors, Monitoring and Forecast.

**Save** keeps Settings open. **Cancel** reloads the saved configuration from the server and replaces edits; a failed reload retains your draft for retry. Leaving with unsaved changes asks you to keep editing or discard them. Reentering Settings loads the saved configuration again.

**Theme mode** offers Auto, Light and Dark. Auto follows Home Assistant's Theme mode inside its interface and falls back to the system preference outside a usable HA context. Light and Dark are local overrides; Auto resumes following the host. Language and theme changes preserve the settings draft. All frontend assets are served locally.

## Updates

- History: 1, 5 or 10 minutes; 5 minutes by default.
- Live average: the latest 60 seconds by default.
- Refresh: every 5 seconds by default.

Use the language menu at the top right to change the page language.

## Results

PR compares actual power with expected power. The power gap is expected power minus actual power. PR may be above 100%, and the power gap may be negative. PR is not shown when expected power is zero.

Energy is counted only when all three sensors have data. Today's energy resets at midnight in your Home Assistant time zone; total energy starts from your first setup.

Choose a language above for the full guide, including settings, output sensors and formulas.

## Generation forecast

Forecast is disabled by default, including after an upgrade. Under **Settings > Forecast**, enable it, enter panel tilt (0–90°), compass direction (north 0°, east 90°, south 180°, west 270°, or a custom value from 0° to below 360°), and NOCT from the datasheet (above 20°C, at most 80°C; default 45°C). Rated power and K are shared with monitoring. Location and time zone come automatically from the saved Home Assistant connection; change them in HA.

Open-Meteo supplies hourly weather for today and the following six local calendar days. Select a date for full-day energy, the hourly power curve and numeric interval details; timestamps include UTC offsets. Today's forecast includes all of today, while **Remaining today** counts only from now to local midnight. Both use the latest successful weather fetch and are separate from settled theoretical energy calculated from sensor readings. Remaining energy decreases as time passes between fetches; a new forecast can also revise the full-day estimate.

Weather normally refreshes hourly; **Refresh forecast** requests an update. Matching cached data survives restart. A failed refresh retains its original fetch time and shows stale data; retries occur after 15 minutes. Data at least two hours old is also stale. Missing weather intervals make affected totals unavailable, with completeness shown separately; missing data is never assumed to be zero. Disabled, missing HA location, initial loading and unavailable states are shown explicitly.

These are theoretical DC reference values for one panel array, using plane-of-array irradiance and a simplified NOCT temperature model. They do not model inverter efficiency/clipping, shading, snow, soiling or system losses and do not guarantee actual AC yield. The four forecast entities are kWh energy values without `state_class`; they can decrease after refresh and are separate from cumulative monitoring energy. They do not provide native HA forecast or Energy dashboard integration.

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
