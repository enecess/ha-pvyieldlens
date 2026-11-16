import os

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


@pytest.fixture
async def theme_page(tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from playwright.async_api import async_playwright
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app
    from test_integration import fake_server

    service = Service(Store(tmp_path / 'data.sqlite'))
    web = create_app(service, Runtime(web_password='theme-test'), run_background=False)
    parent = FastAPI()
    parent.mount('/api/hassio_ingress/ui-check', web)
    async with fake_server(web) as standalone:
        @parent.get('/theme-parent')
        async def host():
            return HTMLResponse('''<!doctype html><html><head><meta name="color-scheme" content="light"></head><body>
<label><input type="radio" name="theme" value="auto" checked>HA Auto</label>
<label><input type="radio" name="theme" value="light">HA Light</label>
<label><input type="radio" name="theme" value="dark">HA Dark</label>
<home-assistant></home-assistant>
<script>
const root = document.querySelector('home-assistant');
const system = matchMedia('(prefers-color-scheme: dark)');
root.hass = {selectedTheme: {theme: 'default'}, themes: {
  default_theme: 'default', default_dark_theme: null, themes: {}, darkMode: system.matches, theme: 'default'
}};
function applyTheme() {
  const choice = document.querySelector('input:checked').value;
  root.hass.selectedTheme = choice === 'auto' ? {theme: 'default'} : {theme: 'default', dark: choice === 'dark'};
  const dark = root.hass.selectedTheme.dark ?? system.matches;
  root.hass.themes = {...root.hass.themes, darkMode: dark};
  document.querySelector('meta[name="color-scheme"]').content = dark ? 'dark' : 'light';
  document.documentElement.style.backgroundColor = dark ? '#111111' : '#ffffff';
}
document.querySelectorAll('input').forEach(input => input.addEventListener('change', applyTheme));
system.addEventListener('change', applyTheme);
applyTheme();
</script>
<iframe id="pvyieldlens-frame" title="PVYieldLens" src="/api/hassio_ingress/ui-check/"></iframe>
</body></html>''')

        @parent.get('/cross-origin')
        async def unavailable_host():
            return HTMLResponse(f'<!doctype html><html><body><iframe id="pvyieldlens-frame" title="PVYieldLens" src="{standalone}/"></iframe></body></html>')

        async with fake_server(parent) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(http_credentials={'username': 'admin', 'password': 'theme-test'})
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            await page.goto(url + '/theme-parent')
            yield page
            assert errors == []
            await browser.close()
    service.store.close()


async def test_ha_light_overrides_system_dark(theme_page):
    from playwright.async_api import expect

    await theme_page.emulate_media(color_scheme='dark')
    await theme_page.get_by_role('radio', name='HA Light', exact=True).check()
    app = theme_page.frame_locator('#pvyieldlens-frame')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'light')
    await expect(app.locator('#theme-select')).to_have_attribute('data-source', 'ha')


async def test_ha_dark_overrides_system_light(theme_page):
    from playwright.async_api import expect

    await theme_page.emulate_media(color_scheme='light')
    await theme_page.get_by_role('radio', name='HA Dark', exact=True).check()
    app = theme_page.frame_locator('#pvyieldlens-frame')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')
    await expect(app.locator('#theme-select')).to_have_attribute('data-source', 'ha')


async def test_auto_tracks_runtime_host_and_system_changes(theme_page):
    from playwright.async_api import expect

    app = theme_page.frame_locator('#pvyieldlens-frame')
    await theme_page.emulate_media(color_scheme='dark')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')
    await theme_page.get_by_role('radio', name='HA Light', exact=True).check()
    await expect(app.locator('html')).to_have_attribute('data-theme', 'light')
    await theme_page.get_by_role('radio', name='HA Auto', exact=True).check()
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')
    await theme_page.emulate_media(color_scheme='light')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'light')


async def test_local_override_persists_and_auto_resumes_ha(theme_page):
    from playwright.async_api import expect

    app = theme_page.frame_locator('#pvyieldlens-frame')
    await theme_page.get_by_role('radio', name='HA Dark', exact=True).check()
    await app.locator('#theme-select').select_option('light')
    await theme_page.emulate_media(color_scheme='dark')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'light')
    await expect(app.locator('#theme-select')).to_have_attribute('data-source', 'manual')
    await theme_page.reload()
    await expect(app.locator('#theme-select')).to_have_value('light')
    await theme_page.get_by_role('radio', name='HA Dark', exact=True).check()
    await app.locator('#theme-select').select_option('auto')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')
    await expect(app.locator('#theme-select')).to_have_attribute('data-source', 'ha')


async def test_cross_origin_parent_and_blocked_storage_use_system(theme_page):
    from playwright.async_api import expect

    await theme_page.context.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError')}})")
    await theme_page.goto(theme_page.url.replace('/theme-parent', '/cross-origin'))
    app = theme_page.frame_locator('#pvyieldlens-frame')
    await theme_page.emulate_media(color_scheme='dark')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')
    await expect(app.locator('#theme-select')).to_have_attribute('data-source', 'system')
    await theme_page.emulate_media(color_scheme='light')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'light')
    await app.locator('#theme-select').select_option('dark')
    await expect(app.locator('html')).to_have_attribute('data-theme', 'dark')


async def test_shell_keeps_data_navigation_visible_in_settings(theme_page):
    from playwright.async_api import expect

    app = theme_page.frame_locator('#pvyieldlens-frame')
    await expect(app.locator('#live-page')).to_be_visible()
    await app.locator('#history-tab').click()
    await expect(app.locator('#history-page')).to_be_visible()
    await app.locator('#settings-button').click()
    await expect(app.locator('#settings-page')).to_be_visible()
    await expect(app.locator('#data-navigation')).to_be_visible()
    await expect(app.locator('#settings-button')).to_contain_text('Settings')
    await app.locator('#forecast-tab').click()
    await expect(app.locator('#forecast-page')).to_be_visible()
