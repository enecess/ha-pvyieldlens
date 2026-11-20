# Changelog

## 0.1.0

Initial stable release.

- Live PV monitoring compares measured inverter power with power estimated from irradiance and module temperature.
- Time-aligned energy and performance ratio (PR) history uses time-weighted integration and persistent energy totals.
- Optional PV module temperature estimation supports monitoring when a measured module temperature is unavailable.
- Seven-day PV power and energy forecasts show original estimates and historical PR correction.
- EMHASS CSV export supports both original and corrected PV power forecasts.
- The dashboard and settings are available in six languages with English fallback.
- Prebuilt Home Assistant App images are available for amd64 and aarch64. PVYieldLens also runs in standalone Docker.
