"""Exercise the production adapter against disposable real Home Assistant Core containers."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

import httpx

from pvyieldlens.engine import calculate
from pvyieldlens.home_assistant import HAState, HomeAssistantClient, entity_payloads, parse_state, source_value
from pvyieldlens.service import Service
from pvyieldlens.settings import MonitoringSettings
from pvyieldlens.storage import Store


VERSIONS = ('2025.9.0', '2025.12.5', '2026.3.4', '2026.6.4', '2026.9.4', '2026.11.0')
PUBLISHERS = ('ghcr.io/home-assistant/home-assistant', 'homeassistant/home-assistant',
              'docker.io/homeassistant/home-assistant')
CONFIGURATION = """homeassistant:
  name: PVYieldLens compatibility
  latitude: 0
  longitude: 0
  elevation: 0
  unit_system: metric
  time_zone: UTC
api:
http:
websocket_api:
onboarding:
history:
recorder:
  commit_interval: 1
sensor:
logger:
  default: warning
"""


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True,
                          timeout=180).stdout.strip()


async def exercise(client, directory):
    checks = {}
    configuration = await client.configuration()
    assert configuration.time_zone == 'UTC'
    assert configuration.location is not None
    assert configuration.location.origin == client.base_url
    assert configuration.location.latitude == 0
    assert configuration.location.longitude == 0
    assert configuration.location.location_name == 'PVYieldLens compatibility'
    assert configuration.location.home_timezone == 'UTC'
    checks['rest_config_location'] = True
    stream = client.events()
    assert await anext(stream) is None

    async def event(entity):
        async with asyncio.timeout(10):
            async for item in stream:
                if item.entity_id == entity:
                    return item
        raise AssertionError('state_changed stream ended')

    async def post(entity, value, unit):
        return await client.request('POST', 'states/' + entity,
                                    json={'state': value, 'attributes': {'unit_of_measurement': unit}})

    started = time.time() - .01
    power = 'sensor.compat_power'
    temp = 'sensor.compat_temperature'
    sun = 'sensor.compat_irradiance'
    for entity, value, unit, role, expected in (
        (power, '1.5', 'kW', 'power', 1500), (temp, '77', '°F', 'temperature', 25),
        (sun, '0.8', 'kW/m²', 'irradiance', 800),
    ):
        await post(entity, value, unit)
        assert parse_state(await event(entity), role)[0].value == expected
    assert {power, temp, sun} <= {item.entity_id for item in await client.states()}
    selected = await client.states((power, temp, sun, 'sensor.compat_missing'))
    missing = await client.http.get(client.base_url + '/api/states/sensor.compat_missing',
                                   headers={'Authorization': 'Bearer ' + client.token})
    assert missing.status_code == 404
    assert selected[-1].state == 'unavailable'
    assert parse_state(selected[-1], 'power')[0].value is None
    checks['rest_states_units_404'] = True

    unusual = 'sensor.compat_non_string_attributes'
    await client.request('POST', 'states/' + unusual, json={'state': '3',
        'attributes': {'friendly_name': {'name': 'Unusual sensor'}, 'unit_of_measurement': ['W']}})
    unusual_event = await event(unusual)
    discovered = {item.entity_id: item for item in await client.states()}
    unusual_selected, temperature = await client.states((unusual, temp))
    for item in (unusual_event, discovered[unusual], unusual_selected):
        assert item.state == '3'
        assert item.attributes.friendly_name is None and item.attributes.unit_of_measurement is None
        assert item.last_updated == unusual_event.last_updated
        assert parse_state(item, 'power')[0].value is None
    assert discovered[temp].attributes.unit_of_measurement == temperature.attributes.unit_of_measurement == '°F'
    assert parse_state(temperature, 'temperature')[0].value == 25
    checks['non_string_attributes_preserve_rest_and_websocket_states'] = True

    tilt, azimuth = 'sensor.compat_tracker_tilt', 'input_number.compat_tracker_azimuth'
    await post(tilt, '0', '°')
    await post(azimuth, '90', '°')
    angles = await client.states((tilt, azimuth))
    assert [row.entity_id for row in angles] == [tilt, azimuth]
    assert [source_value(row.state, row.attributes.unit_of_measurement, axis)
            for row, axis in zip(angles, ('tilt', 'azimuth'), strict=True)] == [0, 90]
    checks['rest_tracker_angles'] = True

    await post(power, '2.5', 'kW')
    changed = await event(power)
    assert parse_state(changed, 'power')[0].value == 2500
    await asyncio.sleep(.05)
    await post(power, '2.5', 'W')
    attributes = await event(power)
    assert attributes.last_changed == changed.last_changed
    assert attributes.last_updated > changed.last_updated
    assert parse_state(attributes, 'power')[0].value == 2.5
    for value, unit in (('25', '°C'), ('298.15', 'K')):
        await post(temp, value, unit)
        assert abs(parse_state(await event(temp), 'temperature')[0].value - 25) < 1e-9
    await post(sun, '800', 'W/m²')
    assert parse_state(await event(sun), 'irradiance')[0].value == 800
    await post(power, 'unavailable', 'W')
    assert parse_state(await event(power), 'power')[0].value is None
    await client.request('DELETE', 'states/' + power)
    removed = await event(power)
    assert removed.state == 'unavailable'
    assert parse_state(removed, 'power')[0].value is None
    await stream.aclose()
    stream = client.events()
    assert await anext(stream) is None
    await post(power, '1000', 'W')
    restored = await event(power)
    assert parse_state(restored, 'power')[0].value == 1000
    checks['websocket_auth_changes_attributes_unavailable_delete_reconnect'] = True

    await asyncio.sleep(.1)
    await post(power, '1000', 'W')
    reported = (await client.states((power,)))[0]
    assert reported.last_updated == restored.last_updated
    assert reported.last_reported > restored.last_reported
    assert parse_state(reported, 'power')[-1].at == reported.last_reported.timestamp()
    cached = await client.request('GET', 'states/' + power)
    checks['unchanged_report_timestamps'] = {'previous': restored.last_reported.isoformat(),
        'rest': cached['last_reported'], 'live_template': reported.last_reported.isoformat()}
    await post('sensor.compat_marker', '1', 'W')
    async with asyncio.timeout(10):
        async for following in stream:
            assert following.entity_id != power, 'unchanged power emitted state_changed'
            if following.entity_id == 'sensor.compat_marker':
                break
        else:
            raise AssertionError('marker event not received')
    await stream.aclose()
    checks['unchanged_last_reported_without_state_changed'] = True

    end = time.time() + .01
    async with asyncio.timeout(30):
        while True:
            history = await client.history([power, temp, sun], started, end)
            if any(item.last_updated == attributes.last_updated for item in history):
                break
            await asyncio.sleep(.5)
    assert all(item.last_reported is None for item in history)
    unit_change = next(item for item in history if item.last_updated == attributes.last_updated)
    assert unit_change.last_changed == changed.last_changed
    assert unit_change.attributes.unit_of_measurement == 'W'
    assert parse_state(unit_change, 'power', historical=True)[0].value == 2.5
    exact = await client.history([power], unit_change.last_updated.timestamp(), end)
    assert exact[0] == unit_change
    checks['recorder_real_state_at_exact_lower_bound'] = True
    boundary = attributes.last_updated.timestamp() + .000123
    raw = await client.request('GET', 'history/period/' + datetime.fromtimestamp(boundary, timezone.utc).isoformat(),
        params={'filter_entity_id': power, 'end_time': datetime.fromtimestamp(end, timezone.utc).isoformat(),
                'significant_changes_only': '0'})
    initial = raw[0][0]
    assert initial['last_changed'] == initial['last_updated']
    assert abs(datetime.fromisoformat(initial['last_updated']).timestamp() - boundary) < .000002
    assert 'last_reported' not in initial
    filtered = await client.history([power], boundary, end)
    assert all(item.last_updated.timestamp() > boundary for item in filtered)
    assert not any(item.last_updated == unit_change.last_updated for item in filtered)
    checks['recorder_full_attributes_no_last_reported_native_skip_initial_state'] = True

    entities = ('sensor.compat_recovery_power', 'sensor.compat_recovery_temperature', 'sensor.compat_recovery_sun')
    config = MonitoringSettings(total_max_power_at_stc_w=5000, pmax_temperature_coefficient_pct_per_c=-.35,
        actual_power_entity=entities[0], module_temperature_entity=entities[1], irradiance_entity=entities[2],
        settlement_interval_minutes=1, actual_power_max_age_seconds=1, module_temperature_max_age_seconds=1,
        irradiance_max_age_seconds=1)
    recovery_start = time.time() - .01
    for entity, value, unit in zip(entities, ('1000', '25', '1000'), ('W', '°C', 'W/m²')):
        await post(entity, value, unit)
    baseline = await client.states(entities)
    store = Store(directory / 'app.sqlite')
    service = Service(store, client)
    await service.configure(config, now=recovery_start, origin=client.base_url)
    await service.ingest(baseline)
    await asyncio.sleep(1.2)
    await service.tick()
    assert service.snapshot()['live_window']['quality'] == 'unavailable'
    for entity, value, unit in zip(entities, ('1000', '25', '1000'), ('W', '°C', 'W/m²')):
        await post(entity, value, unit)
    current = await client.states(entities)
    await service.ingest(current)
    await service.tick()
    assert service.snapshot()['live_window']['quality'] != 'unavailable'
    recovery_end = time.time()
    async with asyncio.timeout(30):
        while True:
            recorded = await client.history(list(entities), recovery_start, recovery_end)
            if len(recorded) == 3:
                break
            await asyncio.sleep(.5)
    assert all(item.last_reported is None for item in recorded)
    assert {item.last_updated for item in recorded} == {item.last_updated for item in baseline}
    points = [point for item in recorded for point in parse_state(item,
        dict(zip(entities, ('power', 'temperature', 'irradiance')))[item.entity_id], historical=True)]
    recovered = calculate(config, points, recovery_start, recovery_end)
    assert 0 < recovered.valid_seconds <= 1
    assert recovered.valid_seconds < recovery_end - recovery_start
    empty = await client.history(list(entities), recovery_end - .1, recovery_end)
    assert empty == []
    await service.recover()
    await service.configure(config.model_copy(update={'total_max_power_at_stc_w': 5001}), now=recovery_end,
                            origin=client.base_url)
    await service.tick()
    committed = store.history(recovery_start, recovery_end)
    total = service.snapshot()['energy_totals']['estimated_energy_lifetime_kwh']
    assert committed and total > 0
    store.close()
    store = Store(directory / 'app.sqlite')
    service = Service(store, client)
    await service.recover()
    await service.tick()
    assert store.history(recovery_start, recovery_end) == committed
    assert service.snapshot()['energy_totals']['estimated_energy_lifetime_kwh'] == total
    store.close()
    checks['service_poll_freshness_conservative_recorder_restart_recovery'] = True
    checks['recorder_recovered_valid_seconds'] = recovered.valid_seconds
    checks['recorder_elapsed_seconds'] = recovery_end - recovery_start

    snapshot = {
        'latest_settled_window': {'estimated_power_w': 5000, 'actual_power_w': 4500, 'pr': 90,
            'revision': 1, 'start': 0, 'end': 60, 'valid_seconds': 60,
            'data_completeness_percent': 100, 'quality': 'complete', 'reason': None},
        'live_window': {'estimated_power_w': 5000, 'actual_power_w': 5500, 'pr': 110,
            'optimizable_power_w': -500, 'start': 30, 'end': 90, 'valid_seconds': 60,
            'data_completeness_percent': 100, 'quality': 'complete', 'reason': None},
        'energy_totals': {'estimated_energy_today_kwh': .1, 'estimated_energy_lifetime_kwh': 1.2,
            'today_allocation_complete': False, 'today_valid_seconds': 60,
            'lifetime_valid_seconds': 600, 'day': '2026-11-13', 'home_timezone': 'UTC', 'settled_until': 60},
        'calculated_at': time.time(), 'revision': 2,
    }
    day_start = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()
    snapshot['forecast'] = {
        'status': 'ready', 'refreshing': False, 'home_timezone': 'UTC',
        'fetched_at': day_start + 3600, 'calculated_at': day_start + 7200, 'last_error': None,
        'today': {'start': day_start, 'end': day_start + 86400, 'forecast_energy_kwh': 2.4,
                  'data_completeness_percent': 100, 'quality': 'complete'},
        'remaining_today': {'start': day_start + 7200, 'end': day_start + 86400, 'forecast_energy_kwh': 1.2,
                            'data_completeness_percent': 100, 'quality': 'complete'},
        'tomorrow': {'start': day_start + 86400, 'end': day_start + 172800, 'forecast_energy_kwh': 3.6,
                     'data_completeness_percent': 100, 'quality': 'complete'},
        'seven_days': {'start': day_start, 'end': day_start + 604800, 'forecast_energy_kwh': 20.4,
                       'data_completeness_percent': 100, 'quality': 'complete'},
    }
    expected = {
        'settled_estimated_power': (5000, 'W', 'power', 'measurement'),
        'settled_actual_power': (4500, 'W', 'power', 'measurement'),
        'settled_pr': (90, '%', None, 'measurement'),
        'estimated_energy_today': (.1, 'kWh', 'energy', 'total_increasing'),
        'estimated_energy_lifetime': (1.2, 'kWh', 'energy', 'total_increasing'),
        'live_estimated_power': (5000, 'W', 'power', 'measurement'),
        'live_actual_power': (5500, 'W', 'power', 'measurement'),
        'live_pr': (110, '%', None, 'measurement'),
        'live_optimizable_power': (-500, 'W', 'power', 'measurement'),
        'forecast_energy_today': (2.4, 'kWh', 'energy', None),
        'forecast_energy_remaining_today': (1.2, 'kWh', 'energy', None),
        'forecast_energy_tomorrow': (3.6, 'kWh', 'energy', None),
        'forecast_energy_7d': (20.4, 'kWh', 'energy', None),
    }
    payloads = entity_payloads(snapshot)
    assert set(payloads) == {'sensor.pvyieldlens_' + name for name in expected}
    await client.publish(payloads)
    checks['published_entities'] = {}
    for name, (value, unit, device_class, state_class) in expected.items():
        entity = 'sensor.pvyieldlens_' + name
        actual = await client.request('GET', 'states/' + entity)
        assert float(actual['state']) == value
        attrs = actual['attributes']
        assert attrs['friendly_name'] == name
        assert attrs['unit_of_measurement'] == unit
        assert attrs.get('device_class') == device_class
        assert attrs.get('state_class') == state_class
        if device_class is None:
            assert 'device_class' not in attrs
        if state_class is None:
            assert 'state_class' not in attrs
        assert attrs == payloads[entity]['attributes']
        if not name.startswith('forecast_'):
            assert attrs['calculated_at'] == snapshot['calculated_at']
            assert attrs['sampling_method'] == 'state_hold'
            assert attrs['configuration_revision'] == (1 if name.startswith('settled_') else 2)
            if name.startswith('estimated_energy_'):
                assert all(attrs[key] == snapshot['energy_totals'][key] for key in (
                    'settled_until', 'day', 'home_timezone', 'today_valid_seconds',
                    'lifetime_valid_seconds', 'today_allocation_complete'))
            else:
                data = snapshot['latest_settled_window' if name.startswith('settled_') else 'live_window']
                assert all(attrs[key] == data[key] for key in (
                    'start', 'end', 'valid_seconds', 'data_completeness_percent', 'quality', 'reason'))
        checks['published_entities'][entity] = {'state': actual['state'], 'attributes': attrs}
    assert (await client.request('GET', 'states/sensor.pvyieldlens_settled_estimated_power'))['attributes']['configuration_revision'] == 1
    for daily, total in ((.2, 1.3), (0, 1.3)):
        snapshot['energy_totals'].update(estimated_energy_today_kwh=daily,
            estimated_energy_lifetime_kwh=total, today_allocation_complete=True)
        await client.publish(entity_payloads(snapshot))
        actual = await client.request('GET', 'states/sensor.pvyieldlens_estimated_energy_today')
        assert float(actual['state']) == daily
        assert actual['attributes']['today_allocation_complete'] is True
        assert float((await client.request('GET', 'states/sensor.pvyieldlens_estimated_energy_lifetime'))['state']) == total
    snapshot.update(latest_settled_window=None, live_window=None)
    await client.publish(entity_payloads(snapshot))
    assert (await client.states(('sensor.pvyieldlens_settled_pr',)))[0].state == 'unavailable'
    checks['monitoring_outputs_allocation_growth_reset_unavailable'] = True

    for name, value, start, end in (
        ('today', 2.4, day_start, day_start + 86400),
        ('remaining_today', 1.2, day_start + 7200, day_start + 86400),
        ('tomorrow', 3.6, day_start + 86400, day_start + 172800),
        ('7d', 20.4, day_start, day_start + 604800),
    ):
        actual = await client.request('GET', 'states/sensor.pvyieldlens_forecast_energy_' + name)
        assert float(actual['state']) == value
        attrs = actual['attributes']
        assert attrs['start'] == start and attrs['end'] == end
        assert attrs['home_timezone'] == 'UTC'
        assert attrs['fetched_at'] == day_start + 3600
        assert attrs['calculated_at'] == day_start + 7200
        assert attrs['data_completeness_percent'] == 100 and attrs['quality'] == 'complete'
        assert attrs['status'] == 'ready' and attrs['refreshing'] is False
        assert attrs['last_error'] is None
    snapshot['forecast']['remaining_today']['forecast_energy_kwh'] = .6
    await client.publish(entity_payloads(snapshot))
    assert float((await client.request('GET',
        'states/sensor.pvyieldlens_forecast_energy_remaining_today'))['state']) == .6
    snapshot['forecast'] = {'status': 'configuration_required'}
    await client.publish(entity_payloads(snapshot))
    for name in ('today', 'remaining_today', 'tomorrow', '7d'):
        actual = await client.request('GET', 'states/sensor.pvyieldlens_forecast_energy_' + name)
        assert actual['state'] == 'unavailable'
        assert actual['attributes']['friendly_name'] == 'forecast_energy_' + name
        assert actual['attributes']['status'] == 'configuration_required'
        assert 'state_class' not in actual['attributes']
    checks['four_forecast_outputs_energy_no_state_class_periods_decrease_configuration_required'] = True
    return checks


async def run_release(version, repository, startup_timeout, workspace):
    image = repository + ':' + version
    identity = json.loads(docker('image', 'inspect', image))[0]
    result = {'requested_version': version, 'image': image, 'image_id': identity['Id'],
        'repo_digests': identity['RepoDigests'], 'architecture': identity['Architecture'],
        'distribution': 'official-publisher-image' if repository in PUBLISHERS else 'official-pypi-core-in-local-image',
        'status': 'failed'}
    prefix = 'pvyieldlens-ha-' + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=prefix + '-', dir=workspace) as temporary:
        directory = Path(temporary)
        (directory / 'configuration.yaml').write_text(CONFIGURATION, encoding='utf-8')
        docker('network', 'create', prefix)
        try:
            docker('run', '-d', '--name', prefix, '--network', prefix, '-p', '127.0.0.1::8123',
                   '-v', f'{directory}:/config', image)
            port = json.loads(docker('inspect', prefix))[0]['NetworkSettings']['Ports']['8123/tcp'][0]['HostPort']
            base = 'http://127.0.0.1:' + port
            async with httpx.AsyncClient(base_url=base, timeout=10, trust_env=False) as http:
                async with asyncio.timeout(startup_timeout):
                    while True:
                        try:
                            response = await http.get('/api/onboarding')
                        except httpx.TransportError:
                            response = None
                        if response is not None and response.status_code == 200:
                            break
                        await asyncio.sleep(.5)
                response = await http.post('/api/onboarding/users', json={'name': 'Compatibility test',
                    'username': 'compatibility', 'password': secrets.token_urlsafe(32), 'client_id': base + '/', 'language': 'en'})
                response.raise_for_status()
                token = await http.post('/auth/token', data={'grant_type': 'authorization_code',
                    'code': response.json()['auth_code'], 'client_id': base + '/'})
                token.raise_for_status()
                client = HomeAssistantClient(base, token.json()['access_token'])
                try:
                    actual = await client.request('GET', 'config')
                    result['runtime_version'] = actual['version']
                    assert actual['version'] == version, 'API runtime does not match requested release'
                    result['checks'] = await exercise(client, directory)
                    result['status'] = 'passed'
                finally:
                    await client.close()
        except (AssertionError, TimeoutError, httpx.HTTPError, ValueError) as error:
            result['error'] = type(error).__name__ + (': ' + str(error) if isinstance(error, AssertionError) else '')
            result['failure_line'] = traceback.extract_tb(error.__traceback__)[-1].lineno
            raise RuntimeError(json.dumps(result)) from None
        finally:
            subprocess.run(['docker', 'rm', '-f', prefix], capture_output=True, timeout=30)
            try:
                if os.getuid() != 0:
                    docker('run', '--rm', '--user', '0:0', '--network', 'none', '--entrypoint', 'chown',
                           '-v', f'{directory}:/config', image, '-Rh', f'{os.getuid()}:{os.getgid()}', '/config')
            finally:
                docker('network', 'rm', prefix)
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions', nargs='+', choices=VERSIONS, default=VERSIONS)
    parser.add_argument('--image-repository', choices=(*PUBLISHERS, 'pvyieldlens-ha-pypi'), default=PUBLISHERS[0])
    parser.add_argument('--startup-timeout', type=int, default=180)
    parser.add_argument('--output', type=Path, default=Path('artifacts/ha-compatibility.json'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = {'tested_at': datetime.now(timezone.utc).isoformat(), 'scope': 'Core API and Recorder on linux/amd64',
               'driver': {'python': sys.version.split()[0], 'platform': platform.platform(),
                          'docker_engine': docker('version', '--format', '{{.Server.Version}}')}, 'results': []}
    for version in args.versions:
        try:
            result = await run_release(version, args.image_repository, args.startup_timeout, args.output.parent.resolve())
        except RuntimeError as error:
            result = json.loads(str(error))
        except subprocess.SubprocessError as error:
            result = {'requested_version': version, 'image': args.image_repository + ':' + version,
                      'status': 'failed', 'error': type(error).__name__}
        results['results'].append(result)
        args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
    return 0 if all(item['status'] == 'passed' for item in results['results']) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
