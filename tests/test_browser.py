import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


async def test_dashboard_configuration_locales_and_mobile(tmp_path):
    from playwright.async_api import async_playwright, expect
    from fake_ha import source_states
    from test_integration import fake_server
    from test_engine import settings
    from pvyieldlens.home_assistant import HAState, parse_state
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        now = time.time()
        await service.configure(settings(interval_minutes=1, update_seconds=1, timezone='Asia/Shanghai'), now=now-1800)
        service.store.add_observations([point for at in range(int(now)-1800,int(now)+1,10)
            for raw,role in zip(source_states(at),('power','temperature','irradiance'))
            for point in parse_state(HAState.model_validate(raw),role)])
        await service.tick(now)
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url, ha_token='simulation-token'))
        async with fake_server(web, lifespan='on') as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(locale='en-US', viewport={'width':1440,'height':1080},
                                                 http_credentials={'username':'admin','password':'browser-test'})
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await expect(page.locator('#live-pr')).to_have_text('90', timeout=15000)
            await expect(page.locator('#history-chart svg')).to_be_visible()
            artifacts = Path('artifacts')
            artifacts.mkdir(exist_ok=True)
            await page.screenshot(path=str(artifacts/'dashboard-desktop.png'), full_page=True)
            await page.get_by_role('button', name='Settings', exact=True).click()
            coefficient = page.locator('[name=temperature_coefficient_pct_per_c]')
            await coefficient.fill('-0.4')
            await page.evaluate("Object.defineProperty(navigator,'languages',{get:()=>['de-DE'],configurable:true}); window.dispatchEvent(new Event('languagechange'))")
            await expect(coefficient).to_have_value('-0.4')
            await expect(page.locator('#coefficient-preview')).to_contain_text('-0,4 %/°C')
            await page.locator('#load-entities').click()
            await expect(page.locator('#connection-result')).to_have_text('Verbindung geprüft')
            await coefficient.fill('-0.35')
            await page.locator('#save-button').click()
            await expect(page.locator('#save-result')).to_have_text('Konfiguration gespeichert')
            assert service.config.temperature_coefficient_pct_per_c == -0.35
            await page.set_viewport_size({'width':390,'height':844})
            await page.screenshot(path=str(artifacts/'configuration-mobile.png'), full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            for locale, language in [('zh-CN','zh'), ('fr-CA','fr'), ('pl-PL','pl'), ('it-IT','it'), ('es-ES','en')]:
                await page.evaluate("locale=>{Object.defineProperty(navigator,'languages',{get:()=>[locale],configurable:true});window.dispatchEvent(new Event('languagechange'))}", locale)
                await expect(page.locator('html')).to_have_attribute('lang', language)
                await expect(coefficient).to_have_value('-0.35')
            from fastapi import FastAPI
            ingress = FastAPI()
            ingress.mount('/api/hassio_ingress/test-prefix', web)
            async with fake_server(ingress) as ingress_url:
                ingress_page = await context.new_page()
                ingress_page.on('pageerror', lambda error: errors.append(str(error)))
                await ingress_page.goto(ingress_url + '/api/hassio_ingress/test-prefix/')
                await expect(ingress_page.locator('#live-pr')).to_have_text('90', timeout=15000)
                await expect(ingress_page.locator('#history-chart svg')).to_be_visible()
                await ingress_page.close()
            assert errors == []
            await browser.close()
