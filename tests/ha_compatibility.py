"""Exercise the production adapter against disposable real Home Assistant Core containers."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import traceback
import uuid

import httpx

from pvyieldlens.engine import calculate
from pvyieldlens.home_assistant import HAState, HomeAssistantClient, entity_payloads, parse_state
from pvyieldlens.service import Service
from pvyieldlens.settings import Settings
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
    assert (await client.configuration()).time_zone == 'UTC'
    checks['rest_config'] = True
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
    config = Settings(rated_power_w=5000, temperature_coefficient_pct_per_c=-.35,
        power_entity=entities[0], temperature_entity=entities[1], irradiance_entity=entities[2],
        interval_minutes=1, power_max_age_seconds=1, temperature_max_age_seconds=1,
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
    assert service.snapshot()['realtime']['quality'] == 'unavailable'
    for entity, value, unit in zip(entities, ('1000', '25', '1000'), ('W', '°C', 'W/m²')):
        await post(entity, value, unit)
    current = await client.states(entities)
    await service.ingest(current)
    await service.tick()
    assert service.snapshot()['realtime']['quality'] != 'unavailable'
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
    await service.configure(config.model_copy(update={'rated_power_w': 5001}), now=recovery_end,
                            origin=client.base_url)
    await service.tick()
    committed = store.history(recovery_start, recovery_end)
    total = service.snapshot()['energy']['total_kwh']
    assert committed and total > 0
    store.close()
    store = Store(directory / 'app.sqlite')
    service = Service(store, client)
    await service.recover()
    await service.tick()
    assert store.history(recovery_start, recovery_end) == committed
    assert service.snapshot()['energy']['total_kwh'] == total
    store.close()
    checks['service_poll_freshness_conservative_recorder_restart_recovery'] = True
    checks['recorder_recovered_valid_seconds'] = recovered.valid_seconds
    checks['recorder_elapsed_seconds'] = recovery_end - recovery_start

    snapshot = {'statistics': {'estimated_power': 5000, 'actual_power': 4500, 'pr': 90, 'revision': 1},
        'realtime': {'estimated_power': 5000, 'actual_power': 5500, 'pr': 110, 'optimizable_power': -500},
        'energy': {'daily_kwh': .1, 'total_kwh': 1.2, 'daily_complete': False},
        'calculated_at': time.time(), 'revision': 2}
    payloads = entity_payloads(snapshot)
    await client.publish(payloads)
    assert len(payloads) == 9
    expected = {'estimated_power': 5000, 'actual_power': 4500, 'pr': 90,
        'daily_estimated_energy': .1, 'total_estimated_energy': 1.2,
        'realtime_estimated_power': 5000, 'realtime_actual_power': 5500,
        'realtime_pr': 110, 'realtime_optimizable_power': -500}
    for name, value in expected.items():
        entity = 'sensor.pvyieldlens_' + name
        actual = await client.request('GET', 'states/' + entity)
        assert float(actual['state']) == value
        attrs = actual['attributes']
        if 'energy' in entity:
            assert attrs['unit_of_measurement'] == 'kWh'
            assert attrs['device_class'] == 'energy'
            assert attrs['state_class'] == 'total_increasing'
            assert attrs['daily_complete'] is False
        elif entity.endswith('_pr'):
            assert attrs['unit_of_measurement'] == '%'
            assert attrs['state_class'] == 'measurement'
            assert 'device_class' not in attrs
        else:
            assert attrs['unit_of_measurement'] == 'W'
            assert attrs['device_class'] == 'power'
            assert attrs['state_class'] == 'measurement'
    assert (await client.request('GET', 'states/sensor.pvyieldlens_estimated_power'))['attributes']['configuration_revision'] == 1
    for daily, total in ((.2, 1.3), (0, 1.3)):
        snapshot['energy'].update(daily_kwh=daily, total_kwh=total, daily_complete=True)
        await client.publish(entity_payloads(snapshot))
        assert float((await client.request('GET', 'states/sensor.pvyieldlens_daily_estimated_energy'))['state']) == daily
        assert float((await client.request('GET', 'states/sensor.pvyieldlens_total_estimated_energy'))['state']) == total
    snapshot.update(statistics=None, realtime=None)
    await client.publish(entity_payloads(snapshot))
    assert (await client.states(('sensor.pvyieldlens_pr',)))[0].state == 'unavailable'
    checks['nine_outputs_metadata_daily_complete_growth_reset_unavailable'] = True
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
               'results': []}
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
