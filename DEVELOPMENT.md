# Development

## Project layout

- `pvyieldlens/src/pvyieldlens/`: configuration, calculations, HA connection, storage and Web server.
- `pvyieldlens/src/pvyieldlens/static/`: HTML, CSS, JavaScript and six language catalogs.
- `pvyieldlens/config.yaml`: Home Assistant App package settings.
- `tests/`: calculation, service, browser and container checks.

The service uses Python 3.13+, FastAPI and SQLite. The browser uses native JavaScript and SVG, with no build step or external CDN.

## Run checks

Run builds and tests in the WSL copy under `/dev-tmp`. From WSL:

```sh
mkdir -p /dev-tmp/ha-pvyieldlens
rsync -a --exclude=.git --exclude=.venv --exclude=.superpowers --exclude=.browsers /mnt/d/UserFiles/AgentTasks/ha-pvyieldlens/ /dev-tmp/ha-pvyieldlens/
cd /dev-tmp/ha-pvyieldlens
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
node --test tests/frontend.test.mjs
```

For browser checks:

```sh
.venv/bin/pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
PVYL_BROWSER_TESTS=1 .venv/bin/pytest -q
```

Browser checks use a local HA simulator and write screenshots to `artifacts/`. They cover setup, charts, language choice, saved preferences, mobile layout and Ingress paths.

For container checks:

```sh
docker build -t pvyieldlens:dev pvyieldlens
.venv/bin/python tests/container_smoke.py
```

The smoke script creates a private test network, two containers and a data volume. It checks collection, configuration, restart recovery and Compose settings, then removes its test resources.

## Data and HA output

The container stores configuration, HA credentials, observations and energy totals under `/data`. Keep this directory when replacing the container. Stop the service before copying the directory for backup.

The service reads current states, events and available history from HA. The nine outputs are REST state entities. They do not provide native entity registry management. REST writes cannot insert past Recorder timestamps; recovered energy appears in HA when it is republished. The app's own history retains the original periods.

The calculation uses time-weighted values from periods where all three inputs are valid. It does not fill missing values with zero. A held state is limited by each source's configured timeout. Configuration changes keep their own effective times; observations from different HA addresses are kept separate.

## Contributions

Use LF line endings and English code comments. Keep user text short and put it in all six language files. User READMEs share one structure and link to each other at the top. Local design and execution records in `docs/superpowers/` and `.superpowers/` are kept out of commits.
