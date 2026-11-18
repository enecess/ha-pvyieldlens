"""Run explicitly in the WSL rsync copy after building pvyieldlens:dev."""
import argparse
import base64
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from urllib.parse import urljoin


class AssetURLs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'script' and values.get('src'):
            self.urls.append(values['src'])
        if tag == 'link' and values.get('rel') == 'stylesheet':
            self.urls.append(values['href'])


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='pvyieldlens:dev')
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), default='linux/amd64')
    args = parser.parse_args()
    prefix = 'pvyieldlens-smoke-' + uuid.uuid4().hex[:8]
    network, volume, fake, app = (prefix + suffix for suffix in ('-net', '-data', '-ha', '-app'))
    root = Path(__file__).resolve().parents[1]
    created = []
    try:
        docker('network', 'create', network)
        created.append(('network', network))
        docker('volume', 'create', volume)
        created.append(('volume', volume))
        docker('run', '-d', '--name', fake, '--network', network, '--network-alias', 'fake-ha',
               '--platform', args.platform, '-v', f'{root / "tests"}:/fixture:ro', args.image,
               'python', '-m', 'uvicorn', 'fake_ha:app', '--app-dir', '/fixture', '--host', '0.0.0.0',
               '--port', '8123', '--ws', 'websockets-sansio', '--log-level', 'critical')
        created.append(('container', fake))
        docker('run', '-d', '--name', app, '--network', network, '--platform', args.platform,
               '-p', '127.0.0.1::8099', '-v', f'{volume}:/data', '-e', 'PVYL_WEB_PASSWORD=smoke-password',
               '-e', 'PVYL_HA_URL=http://fake-ha:8123', '-e', 'PVYL_HA_TOKEN=simulation-token', args.image)
        port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'
        created.append(('container', app))

        def request(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None,
                method='PUT' if body else 'GET', headers={
                    'Authorization':'Basic ' + base64.b64encode(b'admin:smoke-password').decode(),
                    'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)

        def until(predicate, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    result = predicate()
                    if result:
                        return result
                except (urllib.error.URLError, ConnectionError):
                    pass
                time.sleep(0.5)
            raise TimeoutError('container smoke condition not reached')

        def frontend_assets():
            headers = {'Authorization': 'Basic ' + base64.b64encode(b'admin:smoke-password').decode()}
            with urllib.request.urlopen(urllib.request.Request(base + '/', headers=headers), timeout=5) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == 'text/html'
                assert "script-src 'self'" in response.headers['Content-Security-Policy']
                assets = AssetURLs()
                assets.feed(response.read().decode())
            assert any(url.endswith('.js') for url in assets.urls)
            assert any(url.endswith('.css') for url in assets.urls)
            for url in assets.urls:
                assert url.startswith('./assets/')
                with urllib.request.urlopen(urllib.request.Request(urljoin(base + '/', url), headers=headers), timeout=5) as response:
                    assert response.status == 200
                    assert response.headers.get_content_type() in ('text/javascript', 'application/javascript', 'text/css')
                    assert response.headers['X-Content-Type-Options'] == 'nosniff'
                    assert b'simulation-token' not in response.read()
            return len(assets.urls)

        def live_series():
            before = request('/api/snapshot')['energy_totals']
            result = request('/api/live-series')
            after = request('/api/snapshot')['energy_totals']
            assert result['configured'] is True
            assert result['context']['revision'] >= 1
            assert result['context']['monitoring_settings']['update_interval_seconds'] == result['step_seconds'] == 1
            points = result['points']
            assert 1 <= len(points) <= 601
            assert 0 <= result['range']['end'] - result['range']['start'] <= 600
            assert all(result['range']['start'] <= point['at'] <= result['range']['end'] for point in points)
            assert all(left['at'] < right['at'] for left, right in zip(points, points[1:]))
            assert 'segments' not in json.dumps(result)
            assert 'simulation-token' not in json.dumps(result)
            if before['settled_until'] == after['settled_until']:
                assert before['estimated_energy_lifetime_kwh'] == after['estimated_energy_lifetime_kwh']
                assert before['lifetime_valid_seconds'] == after['lifetime_valid_seconds']
            else:
                # Background settlement may advance between the surrounding reads.
                assert after['settled_until'] > before['settled_until']
                assert after['estimated_energy_lifetime_kwh'] >= before['estimated_energy_lifetime_kwh']
                assert after['lifetime_valid_seconds'] >= before['lifetime_valid_seconds']
            return len(points)

        def publication():
            payloads = json.loads(docker('exec', app, 'python', '-c',
                'import json, sys; from pvyieldlens.home_assistant import entity_payloads; '
                'print(json.dumps(entity_payloads(json.loads(sys.argv[1]))))',
                json.dumps(request('/api/snapshot'))))
            expected = {
                'settled_estimated_power': 'W', 'settled_actual_power': 'W', 'settled_pr': '%',
                'estimated_energy_today': 'kWh', 'estimated_energy_lifetime': 'kWh',
                'live_estimated_power': 'W', 'live_actual_power': 'W', 'live_pr': '%',
                'live_optimizable_power': 'W', 'forecast_energy_today': 'kWh',
                'forecast_energy_remaining_today': 'kWh', 'forecast_energy_tomorrow': 'kWh',
                'forecast_energy_7d': 'kWh',
            }
            assert set(payloads) == {'sensor.pvyieldlens_' + name for name in expected}
            for name, unit in expected.items():
                attrs = payloads['sensor.pvyieldlens_' + name]['attributes']
                assert attrs['friendly_name'] == name
                assert attrs['unit_of_measurement'] == unit
            return len(payloads)

        until(lambda: request('/health')['status'] == 'ok')
        fresh = request('/api/config')
        assert fresh['monitoring_settings'] is None
        assert fresh['forecast_settings'] == {
            'enabled': False, 'tilt_deg': None, 'azimuth_deg': None,
            'tilt_entity': None, 'azimuth_entity': None, 'noct_c': 45.0, 'pr_history_days': 14}
        request('/api/config', {'monitoring_settings':{
            'total_max_power_at_stc_w':5000, 'pmax_temperature_coefficient_pct_per_c':-0.35,
            'actual_power_entity':'sensor.power', 'module_temperature_entity':'sensor.temp', 'irradiance_entity':'sensor.sun',
            'settlement_interval_minutes':1, 'update_interval_seconds':1, 'home_timezone':'Asia/Shanghai'}, 'forecast_settings': fresh['forecast_settings']})
        until(lambda: request('/api/snapshot')['connected'])
        until(lambda: request('/api/snapshot')['energy_totals']['estimated_energy_lifetime_kwh'] > 0, timeout=75)
        fresh_live_points = live_series()
        fresh_assets = frontend_assets()
        fresh_outputs = publication()
        assert request('/api/snapshot')['forecast']['status'] == 'disabled'
        config = request('/api/config')
        assert config['forecast_settings'] == {
            'enabled': False, 'tilt_deg': None, 'azimuth_deg': None,
            'tilt_entity': None, 'azimuth_entity': None, 'noct_c': 45.0, 'pr_history_days': 14}
        assert config['location']['latitude'] == 31.23
        assert config['location']['longitude'] == 121.47
        assert config['location']['home_timezone'] == 'Asia/Shanghai'
        forecast = request('/api/forecast')
        assert forecast['status'] == 'disabled' and forecast['fetched_at'] is None
        assert forecast['intervals'] == []
        config['forecast_settings'].update(tilt_deg=25.0, azimuth_deg=180.0, noct_c=47.0)
        request('/api/config', {'monitoring_settings': config['monitoring_settings'], 'forecast_settings': config['forecast_settings']})
        before = request('/api/snapshot')['energy_totals']['estimated_energy_lifetime_kwh']
        docker('stop', '--time', '10', app)
        docker('start', app)
        port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'
        until(lambda: request('/api/snapshot')['connected'])
        after = request('/api/snapshot')['energy_totals']['estimated_energy_lifetime_kwh']
        restart_live_points = live_series()
        restart_assets = frontend_assets()
        restart_outputs = publication()
        assert after >= before > 0
        retained = request('/api/config')
        assert retained['monitoring_settings'] == config['monitoring_settings']
        assert retained['forecast_settings'] == {
            'enabled': False, 'tilt_deg': 25.0, 'azimuth_deg': 180.0,
            'tilt_entity': None, 'azimuth_entity': None, 'noct_c': 47.0, 'pr_history_days': 14}
        forecast = request('/api/forecast')
        assert forecast['status'] == 'disabled' and forecast['fetched_at'] is None
        assert forecast['intervals'] == []
        assert 'simulation-token' not in json.dumps(request('/api/config'))
        subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'config','--quiet'], check=True,
                       env={**os.environ, 'PVYL_WEB_PASSWORD':'smoke-password'})
        print(json.dumps({'container':'passed', 'image':args.image, 'platform':args.platform,
                          'fresh_setup':'passed', 'fresh_outputs':fresh_outputs, 'restart_outputs':restart_outputs,
                          'fresh_bundle_assets':fresh_assets, 'restart_bundle_assets':restart_assets,
                          'fresh_live_points':fresh_live_points, 'restart_live_points':restart_live_points,
                          'forecast_disabled_defaults':'passed', 'restart_persistence':'passed', 'compose':'passed',
                          'energy_before_kwh':before, 'energy_after_kwh':after}))
    finally:
        for kind, name in reversed(created):
            command = ['docker', 'rm', '-f', name] if kind == 'container' else ['docker', kind, 'rm', name]
            subprocess.run(command, capture_output=True)


if __name__ == '__main__':
    main()
