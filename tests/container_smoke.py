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
    parser.add_argument('--legacy-image', default='ghcr.io/enecess/pvyieldlens:0.1.0-beta.1-amd64')
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
        def start(image):
            docker('run', '-d', '--name', app, '--network', network, '--platform', args.platform,
                   '-p', '127.0.0.1::8099', '-v', f'{volume}:/data', '-e', 'PVYL_WEB_PASSWORD=smoke-password',
                   '-e', 'PVYL_HA_URL=http://fake-ha:8123', '-e', 'PVYL_HA_TOKEN=simulation-token', image)
            port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
            return f'http://127.0.0.1:{port}'

        base = start(args.legacy_image)
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

        until(lambda: request('/health')['status'] == 'ok')
        request('/api/config', {'settings':{
            'rated_power_w':5000, 'temperature_coefficient_pct_per_c':-0.35,
            'power_entity':'sensor.power', 'temperature_entity':'sensor.temp', 'irradiance_entity':'sensor.sun',
            'interval_minutes':1, 'update_seconds':1, 'timezone':'Asia/Shanghai'}})
        until(lambda: request('/api/snapshot')['connected'])
        until(lambda: request('/api/snapshot')['energy']['total_kwh'] > 0, timeout=75)
        legacy_total = request('/api/snapshot')['energy']['total_kwh']
        docker('stop', '--time', '10', app)
        docker('rm', app)
        base = start(args.image)
        until(lambda: request('/api/snapshot')['connected'])
        upgraded = request('/api/snapshot')
        upgrade_assets = frontend_assets()
        assert upgraded['energy']['total_kwh'] >= legacy_total > 0
        assert upgraded['forecast']['status'] == 'disabled'
        config = request('/api/config')
        assert config['forecast_settings'] == {
            'enabled': False, 'tilt_deg': None, 'azimuth_deg': None, 'noct_c': 45.0}
        assert config['location']['latitude'] == 31.23
        assert config['location']['longitude'] == 121.47
        assert config['location']['timezone'] == 'Asia/Shanghai'
        forecast = request('/api/forecast')
        assert forecast['status'] == 'disabled' and forecast['fetched_at'] is None
        assert forecast['intervals'] == []
        config['forecast_settings'].update(tilt_deg=25.0, azimuth_deg=180.0, noct_c=47.0)
        request('/api/config', {'settings': config['settings'], 'forecast_settings': config['forecast_settings']})
        before = request('/api/snapshot')['energy']['total_kwh']
        docker('stop', '--time', '10', app)
        docker('start', app)
        port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'
        until(lambda: request('/api/snapshot')['connected'])
        after = request('/api/snapshot')['energy']['total_kwh']
        restart_assets = frontend_assets()
        assert after >= before > 0
        retained = request('/api/config')
        assert retained['settings']['temperature_coefficient_pct_per_c'] == -0.35
        assert retained['forecast_settings'] == {
            'enabled': False, 'tilt_deg': 25.0, 'azimuth_deg': 180.0, 'noct_c': 47.0}
        forecast = request('/api/forecast')
        assert forecast['status'] == 'disabled' and forecast['fetched_at'] is None
        assert forecast['intervals'] == []
        assert 'simulation-token' not in json.dumps(request('/api/config'))
        subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'config','--quiet'], check=True,
                       env={**os.environ, 'PVYL_WEB_PASSWORD':'smoke-password'})
        print(json.dumps({'container':'passed', 'image':args.image, 'platform':args.platform,
                          'legacy_image':args.legacy_image, 'upgrade_persistence':'passed',
                          'upgrade_bundle_assets':upgrade_assets, 'restart_bundle_assets':restart_assets,
                          'forecast_disabled_defaults':'passed', 'restart_persistence':'passed', 'compose':'passed',
                          'legacy_energy_kwh':legacy_total, 'energy_before_kwh':before, 'energy_after_kwh':after}))
    finally:
        for kind, name in reversed(created):
            command = ['docker', 'rm', '-f', name] if kind == 'container' else ['docker', kind, 'rm', name]
            subprocess.run(command, capture_output=True)


if __name__ == '__main__':
    main()
