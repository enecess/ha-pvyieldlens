**English** | [中文](README.zh-CN.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

## Overview

PVYieldLens compares measured solar production with what your PV array is estimated to generate under the observed conditions. Track the performance ratio (PR) in Home Assistant and see a seven-day generation forecast.

## Install

### Home Assistant OS

The App requires Home Assistant 2025.9.0 or newer.

[![Add the PVYieldLens App repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Use the button above and confirm **Add** in Home Assistant. To add the repository manually, open **Settings > Apps > Install app > ⋮ > Repositories** and enter `https://github.com/enecess/ha-pvyieldlens#dev_v0`.
2. Find **PVYieldLens** in the **App store** and select **Install**.
3. Select **Start**, then **Open Web UI**.

Before Home Assistant 2026.2, open **Settings > Add-ons > Add-on store**, then use the ⋮ menu to add the repository.

### Docker

1. Download this repository and open its folder. Copy `.env.example` to `.env` and set `PVYL_WEB_PASSWORD` to your chosen password.
2. Run `docker compose up -d --build`.
3. On the Docker host, open [localhost:8099](http://localhost:8099) and sign in as `admin` with that password.

To allow access from another device, change the port mapping in `compose.yaml` from `127.0.0.1:8099:8099` to `8099:8099`.

## Configure

Open **Settings** in PVYieldLens. Use **Language** at the top right to switch the interface language.

### Home Assistant connection

The Home Assistant App connects automatically. In Docker, enter the **Home Assistant URL** and a **Long-lived access token** from a Home Assistant administrator, then select **Refresh entities**. Administrator access is required to publish the output sensors.

Enter a token on first setup or when changing the URL. With the same URL, leave the field blank to reuse the saved token.

### PV modules

| Setting | What to enter |
| --- | --- |
| **Total max power at STC** | Add up the module ratings in W. Ten 500 W modules total 5,000 W. |
| **Temperature coefficient of Pmax** | Use the datasheet value in %/°C, for example −0.35. |
| **Module tilt** | From 0° to 90°. |
| **Module direction** | Azimuth measured clockwise from north (0°), below 360°. Select a compass preset or **Custom**. |
| **Nominal operating cell temperature (NOCT)** | Use the datasheet value in °C, above 20 °C and up to 80 °C. The default is 45 °C. |

For tilt and direction, choose **Fixed value** or **HA entity** separately. Pick a `sensor.*`, `number.*` or `input_number.*` that reports degrees (°). For a tracker, each forecast refresh uses the angles read at that moment for the full forecast.

*Berlin Demo uses a 5,000 W array tilted at 35° and facing **South · 180°**.*

<!-- screenshot: settings-pv-modules.png -->

### Sensors

| Setting | Sensor and supported units |
| --- | --- |
| **Actual power** | PV generation power in W or kW. |
| **Irradiance** | Irradiance in the plane of the modules, in W/m² or kW/m². |
| **Module temperature (optional)** | Module temperature in °C, °F or K. Leave blank to estimate it from Open-Meteo air temperature, measured irradiance and NOCT. |

*Berlin Demo uses simulated power, irradiance and module temperature sensors.*

<!-- screenshot: settings-sensors.png -->

### Forecast

Under **Forecast** in **Settings**, check the location and time zone. Change them in Home Assistant. Set **Historical PR days** if you want a different history window for forecast correction. The default is 14 days.

### Monitoring settings

By default, PVYieldLens settles energy and PR every 5 minutes. Live values average the latest 60 seconds and refresh every 5 seconds. If a sensor exceeds its **Data timeout**, the affected period counts as missing.

Select **Save configuration**.

## What you get

### Dashboard

Compare current actual and estimated power and check **PR** and **Optimizable power**. **Live data** shows the latest ten minutes of power readings.

*Berlin Demo live power and PR.*

<!-- screenshot: dashboard.png -->

Use **Generation data** to inspect today’s settled power, irradiance and module temperature.

*Today’s settled generation and sensor readings in Berlin Demo.*

<!-- screenshot: dashboard-generation.png -->

**Historical generation** compares daily actual and estimated energy. Choose **7 days**, **30 days** or **Custom** for up to 90 calendar dates. To see the last seven complete days as in Berlin Demo, select **Custom**, end the range yesterday and start it six days before that.

*Berlin Demo daily energy for seven complete dates.*

<!-- screenshot: dashboard-history.png -->

Live PR is actual power divided by estimated power, expressed as a percentage. PR can exceed 100%, and **Optimizable power** (estimated minus actual power) can be negative. Missing readings leave gaps. A measured zero stays zero. When estimated power is zero, PR shows **—**.

### Efficiency

Select **Today**, **24 hours**, **7 days** or **30 days**. **Today** compares with yesterday through the same local time. **7 days** includes today.

Review the range PR, its change in percentage points and estimated minus actual energy. **PR trend** and **Generation comparison** show how performance changes. For calendar ranges, switch between **Daily summary** and the settlement interval. Range PR divides actual energy by estimated energy over the same valid settled periods.

*Berlin Demo efficiency today, compared with yesterday through the same time.*

<!-- screenshot: efficiency.png -->

### Forecast

Compare **Original forecast** and **Corrected forecast** for today and the next six days. The original uses Open-Meteo weather and your array settings. Correction uses recent energy-weighted PR and needs at least three eligible completed days with positive estimated energy. Until then, corrected values show **—**.

See the full day today, **Remaining today** and **Tomorrow’s forecast** in the top cards. **Daily forecast energy** compares all seven dates and gives the **7-day total**. Select **Refresh forecast** to request fresh weather data.

*Berlin Demo original and corrected energy forecasts, date selection and **Export CSV**.*

<!-- screenshot: forecast.png -->

Select a date to compare power curves and open **15-minute details** for interval power, energy, irradiance and temperatures.

*Berlin Demo power curves and 15-minute details for the selected date.*

<!-- screenshot: forecast-details.png -->

For EMHASS with a single PV inverter, select **Export CSV** and choose the original or corrected series. Match the start, interval and step count to your optimization run. Save `data_weather_forecast.csv` in EMHASS’s `data_path`, with `set_use_pv=true` and `weather_forecast_method=csv`. [EMHASS setup details](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

### Home Assistant output sensors

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

The table shows the display names in Home Assistant. Use the full ID in automations, for example `sensor.pvyieldlens_settled_estimated_power`. The four forecast sensors report **Original forecast** energy. Estimated energy for today resets at midnight in your Home Assistant time zone. The lifetime total counts from initial setup.
