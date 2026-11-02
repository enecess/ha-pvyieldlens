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
