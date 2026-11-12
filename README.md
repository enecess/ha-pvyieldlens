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

Open [localhost:8099](http://localhost:8099). Sign in as `admin` with the password you set. In **Settings**, enter your Home Assistant address and a long-lived access token belonging to a Home Assistant **administrator**, then select **Load sensors**. Administrator access is required to publish the output sensors.

The default address works on the Docker host. To open the page from another device, change `127.0.0.1:8099:8099` to `8099:8099` in `compose.yaml`.

## Settings

| Setting | What to enter |
| --- | --- |
| Total rated power | Total panel power in W, e.g. `5000`. |
| Temperature coefficient K | The value from the panel datasheet, in %/°C, e.g. `-0.35`. |
| Power sensor | Your solar generation power sensor (W or kW). |
| Panel temperature | Your panel temperature sensor (°C, °F or K). |
| Sunlight on panels | A sunlight sensor in the same plane as the panels (W/m² or kW/m²). |
| History interval | 1, 5 or 10 minutes. Default: 5 minutes. |
| Average over | Time used to average live readings. Default: 60 seconds. |
| Update every | How often live results refresh. Default: 5 seconds. |

Save your settings, then open **Overview**. The first history result appears when the current period ends. Under **Data timeout**, you can set how long to wait for each sensor before marking its data missing.

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
