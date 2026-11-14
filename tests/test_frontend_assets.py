from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urljoin
from zipfile import ZipFile

import httpx
import pytest
from fastapi import FastAPI

from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from pvyieldlens.web import Runtime, create_app


CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"


@pytest.fixture(scope='module')
def installed_frontend(tmp_path_factory):
    """Catch omitted wheel assets without importing the source checkout."""
    directory = tmp_path_factory.mktemp('installed-frontend')
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'pvyieldlens', directory / 'package',
                    ignore=shutil.ignore_patterns('frontend', 'build', '*.egg-info', '__pycache__'))
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                    '--wheel-dir', str(directory), str(directory / 'package')], check=True, capture_output=True)
    wheel = next(directory.glob('*.whl'))
    with ZipFile(wheel) as package:
        bundled = {name for name in package.namelist() if '/static/' in name}
    generated = {str(path.relative_to(root / 'pvyieldlens/src')) for path in
                 (root / 'pvyieldlens/src/pvyieldlens/static/dist').rglob('*') if path.is_file()}
    assert bundled == generated
    assert any('/assets/' in name for name in bundled)
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(directory / 'venv')], check=True)
    python = directory / 'venv/bin/python'
    subprocess.run([sys.executable, '-m', 'pip', '--python', str(python), 'install', str(wheel)],
                   check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    runner = directory / 'server.py'
    runner.write_text('''from pathlib import Path
import pvyieldlens
from fastapi import FastAPI
from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from pvyieldlens.web import Runtime, create_app
import uvicorn
assert Path(pvyieldlens.__file__).is_relative_to(Path(__file__).parent / 'venv')
app = FastAPI()
app.mount('/api/hassio_ingress/installed-wheel', create_app(Service(Store(Path('data.sqlite'))), Runtime(web_password='installed-test'), run_background=False))
uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
'''.replace('PORT', str(port)))
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    with (directory / 'server.log').open('w') as log:
        process = subprocess.Popen([str(python), '-I', str(runner)], cwd=directory, env=env, stdout=log, stderr=log)
        url = f'http://127.0.0.1:{port}/api/hassio_ingress/installed-wheel/'
        try:
            for _ in range(100):
                assert process.poll() is None, (directory / 'server.log').read_text()
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1', port)) == 0:
                        break
                time.sleep(.05)
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


async def test_installed_frontend_assets_under_ingress(installed_frontend):
    async with httpx.AsyncClient(auth=('admin', 'installed-test')) as client:
        response = await client.get(installed_frontend)
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        assert response.headers['content-security-policy'] == CSP
        assets = AssetURLs()
        assets.feed(response.text)
        assert any(url.endswith('.js') for url in assets.urls)
        assert any(url.endswith('.css') for url in assets.urls)
        for url in assets.urls:
            assert url.startswith('./assets/')
            asset = await client.get(urljoin(installed_frontend, url))
            assert asset.status_code == 200
            assert asset.headers['content-security-policy'] == CSP
            assert asset.headers['x-content-type-options'] == 'nosniff'
            assert asset.headers['content-type'].split(';')[0] in ('text/javascript', 'application/javascript', 'text/css')


@pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')
async def test_installed_frontend_browser_under_ingress(installed_frontend):
    from playwright.async_api import async_playwright, expect

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(http_credentials={'username': 'admin', 'password': 'installed-test'})
        errors, failed = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.on('requestfailed', lambda request: failed.append(request.url))
        page.on('response', lambda response: failed.append(response.url) if response.status >= 400 else None)
        await page.goto(installed_frontend)
        for button, view in [('live-tab', 'live-page'), ('history-tab', 'history-page'),
                             ('forecast-tab', 'forecast-page'), ('settings-button', 'settings-page')]:
            await page.locator('#' + button).click()
            await expect(page.locator('#' + view)).to_be_visible()
        assert errors == []
        assert failed == []
        await browser.close()


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


@pytest.mark.parametrize('prefix', ['', '/api/hassio_ingress/ui-check'])
async def test_compiled_assets_load_relative_to_application_root(tmp_path, prefix):
    service = Service(Store(tmp_path / 'data.sqlite'))
    web = create_app(service, Runtime(web_password='asset-test'), run_background=False)
    app = FastAPI()
    app.mount(prefix or '/', web)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                 auth=('admin', 'asset-test')) as client:
        response = await client.get(prefix + '/')
        assert response.status_code == 200
        assets = AssetURLs()
        assets.feed(response.text)
        assert assets.urls
        assert any(url.endswith('.js') for url in assets.urls)
        assert any(url.endswith('.css') for url in assets.urls)
        for url in assets.urls:
            assert url.startswith('./assets/')
            asset = await client.get(urljoin('http://app' + prefix + '/', url))
            assert asset.status_code == 200
            assert asset.headers['x-content-type-options'] == 'nosniff'
            assert "script-src 'self'" in asset.headers['content-security-policy']
    service.store.close()
