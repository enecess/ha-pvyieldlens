from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
import pytest
from fastapi import FastAPI

from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from pvyieldlens.web import Runtime, create_app


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
