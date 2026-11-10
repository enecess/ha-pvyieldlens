[English](https://github.com/enecess/ha-pvyieldlens/blob/main/README.md) | [中文](https://github.com/enecess/ha-pvyieldlens/blob/main/README.zh-CN.md) | [Français](https://github.com/enecess/ha-pvyieldlens/blob/main/README.fr.md) | [Deutsch](https://github.com/enecess/ha-pvyieldlens/blob/main/README.de.md) | [Polski](https://github.com/enecess/ha-pvyieldlens/blob/main/README.pl.md) | [Italiano](https://github.com/enecess/ha-pvyieldlens/blob/main/README.it.md)

# PVYieldLens

## Get started

1. Open the Web UI and select **Settings**.
2. Select your solar power, panel temperature and sunlight sensors.
3. Enter the total rated power in W and temperature coefficient K in %/°C from your panel datasheet.
4. Save and open **Overview**.

## Updates

- History: 1, 5 or 10 minutes; 5 minutes by default.
- Live average: the latest 60 seconds by default.
- Refresh: every 5 seconds by default.

Use the language menu at the top right to change the page language.

## Results

PR compares actual power with expected power. The power gap is expected power minus actual power. PR may be above 100%, and the power gap may be negative. PR is not shown when expected power is zero.

Energy is counted only when all three sensors have data. Today's energy resets at midnight in your Home Assistant time zone; total energy starts from your first setup.

Choose a language above for the full guide, including settings, output sensors and formulas.

## Installation and connection

The App requires Home Assistant OS with Home Assistant 2025.9.0 or newer. Install and start PVYieldLens from **Settings > Apps > Install app**, then open its Web UI. Versions before 2026.2 use **Settings > Add-ons > Add-on Store**.

The App connects to Home Assistant automatically. For standalone Docker, enter your Home Assistant address and a long-lived access token belonging to a Home Assistant **administrator** in **Settings**. Administrator access is required to publish the output sensors. The full guides above include Docker installation steps.

## Missing data and backups

After an outage, some periods may remain missing. Keep the app's data when updating or reinstalling. Use Home Assistant backups for the App; for standalone Docker, stop the container before copying the `/data` directory.
