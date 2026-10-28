"""Run explicitly in the WSL rsync copy after building pvyieldlens:dev."""
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import urllib.error
import urllib.request


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
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
               '-v', f'{root / "tests"}:/fixture:ro', 'pvyieldlens:dev',
               'python', '-m', 'uvicorn', 'fake_ha:app', '--app-dir', '/fixture', '--host', '0.0.0.0',
               '--port', '8123', '--ws', 'websockets-sansio', '--log-level', 'critical')
        created.append(('container', fake))
        docker('run', '-d', '--name', app, '--network', network, '-p', '127.0.0.1::8099',
               '-v', f'{volume}:/data', '-e', 'PVYL_WEB_PASSWORD=smoke-password',
               '-e', 'PVYL_HA_URL=http://fake-ha:8123', '-e', 'PVYL_HA_TOKEN=simulation-token', 'pvyieldlens:dev')
        created.append(('container', app))
        port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'

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

        until(lambda: request('/health')['status'] == 'ok')
        request('/api/config', {'settings':{
            'rated_power_w':5000, 'temperature_coefficient_pct_per_c':-0.35,
            'power_entity':'sensor.power', 'temperature_entity':'sensor.temp', 'irradiance_entity':'sensor.sun',
            'interval_minutes':1, 'update_seconds':1, 'timezone':'Asia/Shanghai'}})
        until(lambda: request('/api/snapshot')['connected'])
        until(lambda: request('/api/snapshot')['energy']['total_kwh'] > 0, timeout=75)
        before = request('/api/snapshot')['energy']['total_kwh']
        docker('stop', '--time', '10', app)
        docker('start', app)
        port = json.loads(docker('inspect', app))[0]['NetworkSettings']['Ports']['8099/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'
        until(lambda: request('/api/snapshot')['connected'])
        after = request('/api/snapshot')['energy']['total_kwh']
        assert after >= before > 0
        assert request('/api/config')['settings']['temperature_coefficient_pct_per_c'] == -0.35
        assert 'simulation-token' not in json.dumps(request('/api/config'))
        subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'config','--quiet'], check=True,
                       env={**os.environ, 'PVYL_WEB_PASSWORD':'smoke-password'})
        print(json.dumps({'container':'passed','restart_persistence':'passed','compose':'passed',
                          'energy_before_kwh':before,'energy_after_kwh':after}))
    finally:
        for kind, name in reversed(created):
            command = ['docker', 'rm', '-f', name] if kind == 'container' else ['docker', kind, 'rm', name]
            subprocess.run(command, capture_output=True)


if __name__ == '__main__':
    main()
