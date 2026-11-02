# Development

## Project layout

- `pvyieldlens/src/pvyieldlens/`: configuration, calculations, HA connection, storage and Web server.
- `pvyieldlens/src/pvyieldlens/static/`: HTML, CSS, JavaScript and six language catalogs.
- `pvyieldlens/config.yaml`: Home Assistant App package settings.
- `tests/`: calculation, service, browser and container checks.

The service uses Python 3.13+, FastAPI and SQLite. The browser uses native JavaScript and SVG, with no build step or external CDN.

## App repository distribution

The source-build repository structure is already in place: `repository.yaml` provides root metadata, and `pvyieldlens/config.yaml` and `pvyieldlens/Dockerfile` define the App. The config omits `image`, so Supervisor builds the Dockerfile during installation. See the official [repository guide](https://contributors.home-assistant.io/apps/guides/repository/) and [App file reference](https://contributors.home-assistant.io/apps/reference/files/).

For a public release, publish the complete tracked App files to the default `main` branch and make the Git repository readable to Home Assistant devices. The stable repository URL is `https://github.com/enecess/ha-pvyieldlens`. A `#branch` suffix can be used for testing, but Supervisor treats it as a separate repository and App identity.

For local development, copy `pvyieldlens` to `/addons/pvyieldlens` on the Home Assistant OS host, reload the local Apps list in the App store, then install and start PVYieldLens. Apps are supported on Home Assistant OS; Home Assistant Container users run the independent Docker service. See [Apps and integrations](https://www.home-assistant.io/docs/apps-and-integrations/). Live installation on Home Assistant OS, including ARM hardware, remains untested.

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
