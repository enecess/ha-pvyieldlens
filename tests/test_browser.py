import asyncio
import json
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


async def assert_sensor_candidates(page, role, entity_ids):
    from playwright.async_api import expect

    control = page.locator(f'[name={role}_entity]')
    await expect(control).to_be_enabled()
    original = await control.input_value()
    await control.fill('')
    await control.click()
    menu = page.locator('#' + await control.get_attribute('aria-controls'))
    await expect(control).to_have_attribute('aria-expanded', 'true')
    await expect(menu).to_have_attribute('role', 'listbox')
    await expect(menu.get_by_role('option')).to_have_count(len(entity_ids))
    if entity_ids:
        await expect(menu).to_be_visible()
        await expect(menu.get_by_role('option')).to_contain_text(entity_ids)
    else:
        await expect(page.locator('.sensor-empty')).to_be_visible()
    await control.fill(original)
    await control.press('Escape')
    await expect(control).to_have_value(original)
    await expect(menu).not_to_be_visible()


async def test_settings_leave_cancel_and_discard(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#history-tab').click()
    await page.locator('#history-range [data-value="7d"]').click()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    before = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
    await page.locator('#history-tab').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#settings-button')).to_have_attribute('aria-current', 'page')
    await expect(page.locator('#keep-editing')).to_be_focused()
    await page.keyboard.press('Tab')
    await expect(page.locator('#discard-changes')).to_be_focused()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Enter')
    await expect(page.locator('dialog')).not_to_be_visible()
    await expect(page.locator('#history-tab')).to_be_focused()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
    await page.locator('#history-tab').click()
    await page.keyboard.press('Escape')
    await expect(page.locator('dialog')).not_to_be_visible()
    await expect(page.locator('#history-tab')).to_be_focused()
    await page.locator('#history-tab').click()
    await page.locator('#discard-changes').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('#history-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')


async def test_same_page_settings_keeps_scroll_and_draft(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    reads = []
    page.on('request', lambda request: reads.append(request.url) if request.url.endswith('/api/config') else None)
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    before = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
    count = len(reads)
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    assert len(reads) == count
    assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
    await expect(page.locator('dialog')).not_to_be_visible()


async def test_brand_uses_leave_guard(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await page.locator('.brand').click()
    await expect(page.locator('dialog')).to_be_visible()
    await page.locator('#keep-editing').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    await expect(page.locator('.brand')).to_be_focused()
    await page.locator('.brand').click()
    await page.locator('#discard-changes').click()
    await expect(page.locator('#live-page')).to_be_visible()


@pytest.mark.parametrize('reverted', [False, True])
async def test_clean_settings_leaves_without_confirmation(browser_workspace, reverted):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('#save-button')).to_be_disabled()
    if reverted:
        await page.locator('button[data-settings-category=modules]').click()
        await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
        await page.locator('[name=total_max_power_at_stc_w]').fill('5000.0')
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('dialog')).not_to_be_visible()


async def test_data_pages_and_gear_settings_preserve_context(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    history_requests = []
    page.on('request', lambda request: history_requests.append(request.url) if '/api/history?' in request.url else None)
    await expect(page.locator('#live-page')).to_be_visible()
    await expect(page.locator('#history-page')).to_be_hidden()
    await expect(page.locator('#forecast-page')).to_be_hidden()
    assert history_requests == []
    await page.locator('#history-tab').click()
    await page.locator('#history-range [data-value="7d"]').click()
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#data-navigation')).to_be_visible()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=pmax_temperature_coefficient_pct_per_c]').fill('-0.4')
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[data-settings-section=modules]')).to_be_visible()
    await expect(page.locator('[data-settings-section=forecast]')).to_be_visible()
    await expect(page.locator('#save-button')).to_be_enabled()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=modules]').click()
    await expect(page.locator('[name=pmax_temperature_coefficient_pct_per_c]')).to_have_value('-0.4')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.monitoring_settings.pmax_temperature_coefficient_pct_per_c == -0.4
    await expect(page.locator('#ha-token')).to_have_value('')
    await expect(page.locator('#save-button')).to_be_disabled()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-page')).to_be_visible()
    await expect(page.locator('#live-page')).to_be_hidden()
    await expect(page.locator('#history-page')).to_be_hidden()


@pytest.mark.parametrize('width', [700, 768])
async def test_french_tablet_settings_returns_to_selected_history_range(browser_workspace, width):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option('fr')
    await page.locator('#history-tab').click()
    await page.locator('#history-range [data-value="7d"]').click()
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#data-navigation')).to_be_visible()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6000')
    await expect(page.locator('#save-button')).to_be_enabled()
    await page.locator('#discard-settings-changes').click()
    await expect(page.locator('#save-button')).to_be_disabled()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('#history-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    assert await page.evaluate('scrollX') == 0


@pytest.mark.parametrize('browser_workspace', [False], indirect=True)
async def test_settings_reveals_first_invalid_category(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    assert 'undefined' not in await page.locator('#live-page').inner_text()
    assert 'NaN' not in await page.locator('#live-page').inner_text()
    await expect(page.locator('#live-estimated')).to_have_text('—')
    await page.locator('#open-settings').click()
    await expect(page.get_by_label('Total max power at STC', exact=False)).to_have_value('')
    await expect(page.get_by_label('Temperature coefficient of Pmax', exact=False)).to_have_value('')
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('5000')
    await page.locator('[name=pmax_temperature_coefficient_pct_per_c]').fill('-0.35')
    await page.locator('button[data-settings-category=forecast]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('button[data-settings-category=sources]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('[name=actual_power_entity]')).to_be_focused()
    assert service.monitoring_settings is None
    await page.locator('[name=actual_power_entity]').fill('sensor.power')
    await page.locator('[name=module_temperature_entity]').fill('sensor.temp')
    await page.locator('[name=irradiance_entity]').fill('sensor.sun')
    await page.locator('button[data-settings-category=forecast]').click()
    await page.locator('[name=forecast_enabled]').check()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_tilt_deg]')).to_be_focused()
    await expect(page.locator('[data-settings-section=forecast]')).to_be_visible()


async def test_forecast_settings_round_trip_and_server_error_category(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('45')
    await page.locator('[name=forecast_enabled]').check()
    await page.locator('[name=forecast_tilt_deg]').fill('25')
    await page.locator('#forecast-direction').select_option('180')
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('180')
    await page.locator('#forecast-direction').select_option('custom')
    await page.locator('[name=forecast_azimuth_deg]').fill('360')
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_be_focused()
    await expect(page.locator('#save-result')).to_be_empty()
    await page.locator('[name=forecast_azimuth_deg]').fill('123.5')
    await page.locator('[name=forecast_noct_c]').fill('20')
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_be_focused()
    await expect(page.locator('#save-result')).to_be_empty()
    await page.locator('[name=forecast_noct_c]').fill('46')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.model_dump() == {'enabled': True, 'tilt_deg': 25, 'azimuth_deg': 123.5,
        'tilt_entity': None, 'azimuth_entity': None, 'noct_c': 46, 'pr_history_days': 14}
    await page.reload()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('46')
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('123.5')
    await expect(page.locator('#forecast-direction')).to_have_value('custom')
    await page.locator('[name=forecast_enabled]').uncheck()
    await page.locator('[name=forecast_tilt_deg]').fill('')
    await page.locator('[name=forecast_azimuth_deg]').fill('')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.tilt_deg is None and service.forecast.settings.azimuth_deg is None
    await page.reload()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('46')
    await expect(page.locator('[name=forecast_enabled]')).not_to_be_checked()
    await expect(page.locator('[name=forecast_tilt_deg]')).to_have_value('')
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('')
    await expect(page.locator('#forecast-direction')).to_have_value('')
    await page.route('**/api/config', lambda route: route.fulfill(status=422, json={
        'error': 'invalid_configuration', 'fields': ['monitoring_settings.actual_power_max_age_seconds']}))
    await page.locator('[name=forecast_noct_c]').fill('47')
    await page.locator('#save-button').click()
    await expect(page.locator('button[data-settings-category=monitoring]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('[name=actual_power_max_age_seconds]')).to_be_focused()
    await expect(page.locator('[name=actual_power_max_age_seconds]')).to_be_in_viewport()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('47')
    await expect(page.locator('#save-button')).to_be_enabled()


async def test_monitoring_timeouts_are_directly_visible(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=monitoring]').click()
    for name, value in [('actual_power_max_age_seconds', '900'), ('module_temperature_max_age_seconds', '900'), ('irradiance_max_age_seconds', '900')]:
        field = page.locator(f'[name={name}]')
        await expect(field).to_be_visible()
        await expect(field).to_have_value(value)
        await field.focus()
        await expect(field).to_be_focused()
        await expect(field).to_be_in_viewport()


async def test_settings_trims_pasted_entity_ids_before_native_validation(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=sources]').click()
    for name, value in [('actual_power_entity', ' sensor.power '), ('module_temperature_entity', ' sensor.temp '), ('irradiance_entity', ' sensor.sun ')]:
        await page.locator(f'[name={name}]').fill(value)
        await expect(page.locator(f'[name={name}]')).to_have_value(value)
    await expect(page.locator('#save-button')).to_be_disabled()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.monitoring_settings.total_max_power_at_stc_w == 6100
    assert service.monitoring_settings.actual_power_entity == 'sensor.power'
    assert service.monitoring_settings.module_temperature_entity == 'sensor.temp'
    assert service.monitoring_settings.irradiance_entity == 'sensor.sun'
    await expect(page.locator('[name=actual_power_entity]')).to_have_value('sensor.power')
    await expect(page.locator('#save-button')).to_be_disabled()


@pytest.mark.parametrize('source', [' sensor.temp ', ' sensor.pvyieldlens_output '])
async def test_settings_rejects_normalized_duplicate_and_output_sources(browser_workspace, source):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('[name=actual_power_entity]').fill(source)
    await page.locator('#save-button').click()
    await expect(page.locator('[name=actual_power_entity]')).to_be_focused()
    await expect(page.locator('[name=actual_power_entity]')).to_have_attribute('aria-invalid', 'true')
    assert await page.locator('[name=actual_power_entity]').evaluate('node => node.validity.customError')
    assert service.monitoring_settings.actual_power_entity == 'sensor.power'


async def test_settings_success_expires_after_three_seconds_without_reset(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.emulate_media(reduced_motion='reduce')
    await page.clock.install(time=0)
    await page.clock.pause_at(1000)
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=forecast]').click()
    await page.locator('[name=forecast_noct_c]').fill('46')
    await page.clock.run_for(32)
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    await page.locator('[name=forecast_noct_c]').focus()
    before = await page.evaluate('''() => ({scroll: document.querySelector('#settings-scroll').scrollTop,
        section: document.querySelector('[data-settings-category][aria-pressed=true]').dataset.settingsCategory})''')
    await page.clock.run_for(2999)
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    await page.clock.run_for(1)
    await expect(page.locator('#save-result')).to_be_empty()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('46')
    await expect(page.locator('[name=forecast_noct_c]')).to_be_focused()
    await expect(page.locator('#save-button')).to_be_disabled()
    assert service.forecast.settings.noct_c == 46
    after = await page.evaluate('''() => ({scroll: document.querySelector('#settings-scroll').scrollTop,
        section: document.querySelector('[data-settings-category][aria-pressed=true]').dataset.settingsCategory})''')
    assert after == before


async def test_settings_success_timeout_does_not_erase_a_newer_failure(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.clock.install(time=0)
    await page.clock.pause_at(1000)
    await page.locator('#settings-button').click()
    await page.locator('[name=forecast_noct_c]').fill('46')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    await page.route('**/api/config', lambda route: route.fulfill(status=502, json={'error': 'ha_connection_failed'}))
    await page.locator('[name=forecast_noct_c]').fill('47')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_contain_text('Cannot reach Home Assistant')
    await page.clock.run_for(3000)
    await expect(page.locator('#save-result')).to_contain_text('Cannot reach Home Assistant')
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('47')
    await expect(page.locator('#save-button')).to_be_enabled()


async def test_locales_storage_fallback_and_ingress(browser_workspace):
    from playwright.async_api import expect
    from fastapi import FastAPI
    from test_integration import fake_server

    page, _, web = browser_workspace
    for locale, language in [('zh-CN', 'zh'), ('fr-CA', 'fr'), ('pl-PL', 'pl'), ('it-IT', 'it'), ('es-ES', 'en')]:
        await page.evaluate("locale => {Object.defineProperty(navigator, 'languages', {get: () => [locale], configurable: true}); window.dispatchEvent(new Event('languagechange'));}", locale)
        await expect(page.locator('html')).to_have_attribute('lang', language)
    await page.locator('#language-select').select_option('fr')
    await page.reload()
    await expect(page.locator('html')).to_have_attribute('lang', 'fr')
    await page.locator('#language-select').select_option('auto')
    blocked = await page.context.new_page()
    await blocked.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError')}})")
    await blocked.goto(page.url)
    await expect(blocked.locator('main')).to_have_attribute('data-configuration-ready', 'true')
    await blocked.locator('#language-select').select_option('zh')
    await expect(blocked.locator('html')).to_have_attribute('lang', 'zh')
    await blocked.close()
    ingress = FastAPI()
    # The running app is mounted through a relative Ingress prefix.
    ingress.mount('/api/hassio_ingress/test-prefix', web)
    async with fake_server(ingress) as url:
        await page.goto(url + '/api/hassio_ingress/test-prefix/')
        await expect(page.locator('main')).to_have_attribute('data-configuration-ready', 'true')
        await page.locator('#history-tab').click()
        await expect(page.locator('#history-chart .chart-empty')).to_be_visible()
        await page.locator('#settings-button').click()
        await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])


async def test_sensor_suggestions_filter_select_and_preserve_manual_drafts(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    saves = []
    page.on('request', lambda request: saves.append(request) if request.url.endswith('/api/config') and request.method == 'PUT' else None)
    await page.route('**/api/connection', lambda route: route.fulfill(json={
        'home_timezone': 'UTC', 'location': None,
        'entities': [
            {'entity_id': 'sensor.roof_power', 'name': 'Roof inverter', 'unit': 'W', 'state': '1'},
            {'entity_id': 'sensor.garage_power', 'name': 'Garage inverter', 'unit': 'kW', 'state': '2'},
            {'entity_id': 'sensor.outdoor_temperature', 'name': 'Outdoor temperature', 'unit': '°F', 'state': '3'},
            {'entity_id': 'sensor.roof_irradiance', 'name': 'Roof irradiance', 'unit': 'W/m²', 'state': '4'},
            {'entity_id': 'sensor.pvyieldlens_output', 'name': 'Feedback', 'unit': 'W', 'state': '5'},
            {'entity_id': 'sensor.battery', 'name': 'Battery', 'unit': '%', 'state': '6'},
        ]}))
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await page.locator('[data-settings-category=sources]').click()
    power = page.get_by_role('combobox', name='Actual power', exact=True)
    await power.fill('INVERTER')
    await expect(power).to_have_attribute('aria-expanded', 'true')
    menu_id = await power.get_attribute('aria-controls')
    menu = page.locator(f'#{menu_id}')
    await expect(menu).to_have_attribute('role', 'listbox')
    await expect(menu.get_by_role('option')).to_have_count(2)
    await expect(menu).to_contain_text('sensor.roof_power')
    await expect(menu).to_contain_text('Garage inverter')
    for key in ['ArrowDown', 'Enter', 'Escape']:
        assert not await power.evaluate('''(input, key) => {
            const event = new KeyboardEvent('keydown', {key, isComposing: true, bubbles: true, cancelable: true});
            input.dispatchEvent(event);
            return event.defaultPrevented;
        }''', key)
    await expect(power).to_have_value('INVERTER')
    await expect(power).not_to_have_attribute('aria-activedescendant')
    await expect(power).to_have_attribute('aria-expanded', 'true')
    await power.press('ArrowDown')
    first = menu.get_by_role('option').first
    await expect(first).to_have_attribute('aria-selected', 'true')
    await expect(power).to_have_attribute('aria-activedescendant', await first.get_attribute('id'))
    await expect(power).to_be_focused()
    await expect(power).to_have_value('INVERTER')
    await power.press('ArrowDown')
    await power.press('ArrowUp')
    await power.press('Enter')
    await expect(power).to_have_value('sensor.roof_power')
    await expect(power).to_have_attribute('aria-expanded', 'false')
    assert saves == []
    assert service.monitoring_settings.actual_power_entity == 'sensor.power'
    await power.fill('garage_power')
    await expect(menu.get_by_role('option')).to_have_count(1)
    await menu.get_by_role('option').click()
    await expect(power).to_have_value('sensor.garage_power')
    await expect(power).to_be_focused()
    await expect(power).to_have_accessible_name('Actual power')
    await power.fill('sensor.manual_not_discovered')
    await expect(menu.get_by_role('option')).to_have_count(0)
    await expect(page.get_by_role('status').filter(has_text='No matching sensors')).to_be_visible()
    await power.press('Escape')
    await expect(power).to_have_attribute('aria-expanded', 'false')
    await expect(power).to_have_value('sensor.manual_not_discovered')
    await power.press('ArrowDown')
    await power.press('Tab')
    await expect(power).to_have_attribute('aria-expanded', 'false')
    await expect(page.locator('[name=module_temperature_entity]')).to_be_focused()
    for field, name, entity in [
        ('module_temperature_entity', 'Module temperature', 'sensor.outdoor_temperature'),
        ('irradiance_entity', 'Irradiance', 'sensor.roof_irradiance'),
    ]:
        control = page.get_by_role('combobox', name=name, exact=True)
        await control.fill('')
        options = page.locator('#' + await control.get_attribute('aria-controls')).get_by_role('option')
        await expect(options).to_have_count(1)
        await options.click()
        await expect(page.locator(f'[name={field}]')).to_have_value(entity)
    await power.fill('')
    await expect(menu.get_by_role('option')).to_have_count(2)
    await power.press('ArrowUp')
    await power.press('Escape')
    await expect(power).to_have_value('')
    await power.fill('sensor.manual_not_discovered')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.monitoring_settings.actual_power_entity == 'sensor.manual_not_discovered'
    await power.click()
    await page.locator('#history-tab').click()
    await expect(menu).not_to_be_visible()


@pytest.mark.parametrize('shortcut, selection, active_index', [
    ('Shift+ArrowUp', [0, 7], 1),
    ('Shift+ArrowDown', [7, 17], 0),
])
async def test_sensor_shifted_arrows_preserve_native_text_selection(browser_workspace, shortcut, selection, active_index):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.route('**/api/connection', lambda route: route.fulfill(json={
        'home_timezone': 'UTC', 'location': None,
        'entities': [
            {'entity_id': 'sensor.roof_power', 'name': 'Roof inverter', 'unit': 'W', 'state': '1'},
            {'entity_id': 'sensor.roof_power_backup', 'name': 'Backup inverter', 'unit': 'W', 'state': '2'},
        ]}))
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await page.locator('[data-settings-category=sources]').click()
    power = page.get_by_role('combobox', name='Actual power', exact=True)
    await power.fill('sensor.roof_power')
    options = page.get_by_role('listbox').get_by_role('option')
    await expect(options).to_have_count(2)
    await power.press('ArrowDown')
    await expect(options.nth(0)).to_have_attribute('aria-selected', 'true')
    await power.press('ArrowDown')
    await expect(options.nth(1)).to_have_attribute('aria-selected', 'true')
    await power.press('ArrowUp')
    await expect(options.nth(0)).to_have_attribute('aria-selected', 'true')
    if active_index == 1:
        await power.press('ArrowDown')
    active_id = await options.nth(active_index).get_attribute('id')
    await expect(power).to_have_attribute('aria-activedescendant', active_id)
    await power.evaluate('(input) => input.setSelectionRange(7, 7)')
    await power.press(shortcut)
    assert await power.evaluate('''input => ({
        selection: [input.selectionStart, input.selectionEnd],
        active: input.getAttribute('aria-activedescendant'),
    })''') == {'selection': selection, 'active': active_id}
    await expect(options.nth(active_index)).to_have_attribute('aria-selected', 'true')
    await expect(page.get_by_role('listbox').get_by_role('option', selected=True)).to_have_count(1)
    await expect(power).to_have_value('sensor.roof_power')
    await expect(power).to_be_focused()
    await power.press('Shift+Tab')
    await expect(page.locator('[name=pmax_temperature_coefficient_pct_per_c]')).to_be_focused()
    await expect(power).to_have_attribute('aria-expanded', 'false')
    await expect(page.get_by_role('listbox')).not_to_be_visible()


async def test_sensor_keyboard_selection_survives_unchanged_location_poll(browser_workspace):
    from playwright.async_api import expect
    from pvyieldlens.settings import HALocation

    page, service, _ = browser_workspace
    response = await page.request.get(page.url + 'api/config')
    await service.configure(service.monitoring_settings, origin=(await response.json())['connection']['url'])
    service.forecast.configure(service.monitoring_settings, service.forecast.settings, service.origin,
        HALocation(origin=service.origin, latitude=1.0, longitude=2.0, location_name='Active', home_timezone='UTC'))
    await page.reload()
    await expect(page.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await expect(page.locator('#forecast-location')).to_have_text('Active · 1, 2')
    await page.locator('[data-settings-category=sources]').click()
    control = page.get_by_role('combobox', name='Actual power', exact=True)
    await control.fill('')
    await control.press('ArrowDown')
    option = page.get_by_role('listbox').get_by_role('option')
    await expect(option).to_have_attribute('aria-selected', 'true')
    active_id = await option.get_attribute('id')
    await expect(control).to_have_attribute('aria-activedescendant', active_id)
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')) as update:
        pass
    assert (await (await update.value).json())['location'] == {
        'origin': service.origin, 'latitude': 1.0, 'longitude': 2.0, 'location_name': 'Active', 'home_timezone': 'UTC'}
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    await expect(control).to_be_focused()
    await expect(control).to_have_value('')
    await expect(control).to_have_attribute('aria-activedescendant', active_id)
    await expect(option).to_have_attribute('aria-selected', 'true')
    await control.press('Enter')
    await expect(control).to_have_value('sensor.power')
    await expect(control).to_have_attribute('aria-expanded', 'false')


@pytest.mark.parametrize('selection', ['pointer', 'keyboard'])
async def test_sensor_selection_clears_server_field_feedback(browser_workspace, selection):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await page.locator('[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6000')
    await page.route('**/api/config', lambda route: route.fulfill(status=422, json={
        'error': 'invalid_configuration', 'fields': ['monitoring_settings.actual_power_entity']}))
    await page.locator('#save-button').click()
    power = page.get_by_role('combobox', name='Actual power', exact=True)
    await expect(power).to_be_focused()
    await expect(power).to_have_attribute('aria-invalid', 'true')
    await expect(power).to_have_attribute('aria-expanded', 'true')
    if selection == 'keyboard':
        await power.press('ArrowDown')
        await power.press('Enter')
    else:
        await page.get_by_role('option').filter(has_text='sensor.power').click()
    await expect(power).not_to_have_attribute('aria-invalid', 'true')
    await expect(page.locator('#save-result')).to_be_empty()
    await expect(power).to_have_value('sensor.power')
    await expect(power).to_be_focused()


async def test_sensor_menu_closes_when_input_scrolls_out_of_settings(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await page.locator('[data-settings-category=sources]').click()
    control = page.get_by_role('combobox', name='Actual power', exact=True)
    await control.fill('')
    await expect(control).to_have_attribute('aria-expanded', 'true')
    await page.locator('#settings-scroll').evaluate('''container => container.scrollTo({
        top: container.scrollTop + document.querySelector('[name=actual_power_entity]').getBoundingClientRect().bottom
            - container.getBoundingClientRect().top + 20, behavior: 'instant'})''')
    await expect(control).to_have_attribute('aria-expanded', 'false')
    await expect(page.get_by_role('listbox')).not_to_be_visible()


async def test_sensor_menu_closes_when_outer_content_clips_input_behind_header(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.set_viewport_size({'width': 390, 'height': 430})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#language-select').select_option('de')
    await page.locator('#settings-button').click()
    await expect(page.locator('#load-entities')).to_be_enabled()
    await page.locator('[data-settings-category=sources]').click()
    control = page.locator('[name=actual_power_entity]')
    # Leave enough outer scroll range to hide the input despite localized label wrapping.
    await control.evaluate('''input => {
        const outer = document.querySelector('#content-scroll');
        const inner = document.querySelector('#settings-scroll');
        const header = document.querySelector('.app-header').getBoundingClientRect();
        inner.scrollTop += Math.max(0, input.getBoundingClientRect().bottom
            - (outer.scrollHeight - outer.clientHeight - outer.scrollTop) - header.bottom + 1);
    }''')
    await control.fill('missing')
    await expect(control).to_have_attribute('aria-expanded', 'true')
    await expect(page.locator('.sensor-suggestions')).to_be_visible()
    initial = await page.locator('.sensor-suggestions').bounding_box()
    content = await page.locator('#content-scroll').bounding_box()
    dock = await page.locator('#settings-actions').bounding_box()
    assert initial['y'] >= content['y']
    assert initial['y'] + initial['height'] <= dock['y'] - 3
    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
    await page.wait_for_function("() => document.querySelector('[name=actual_power_entity]').getBoundingClientRect().bottom <= document.querySelector('.app-header').getBoundingClientRect().bottom")
    clipped = await control.bounding_box()
    await expect(control).to_have_attribute('aria-expanded', 'false')
    await expect(page.locator('.sensor-suggestions')).not_to_be_visible()
    assert await page.evaluate('scrollY') == 0
    assert (await page.locator('.app-header').bounding_box())['y'] == 0
    artifacts = Path(os.getenv('PVYL_SENSOR_ARTIFACTS', 'artifacts/task-2-sensors'))
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / 'sensor-outer-clipped-390-430.json').write_text(json.dumps({
        'initial_menu': initial, 'content': content, 'dock': dock, 'clipped_input': clipped}, indent=2), encoding='utf-8')
    await page.screenshot(path=str(artifacts / 'sensor-outer-clipped-390-430.png'))


@pytest.mark.parametrize(('width', 'height', 'theme'), [
    (1440, 900, 'light'), (1440, 900, 'dark'), (390, 844, 'light'),
    (390, 844, 'dark'), (390, 480, 'dark'), (320, 480, 'light'),
])
async def test_sensor_menu_viewport_geometry_and_active_scroll(browser_workspace, width, height, theme):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    errors = []
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    await page.set_viewport_size({'width': width, 'height': height})
    await page.locator('#theme-select').select_option(theme)
    await page.route('**/api/connection', lambda route: route.fulfill(json={
        'home_timezone': 'UTC', 'location': None,
        'entities': [{'entity_id': f'sensor.long_roof_inverter_power_{index:02}',
                      'name': f'Roof inverter with a very long descriptive friendly name for the south array {index:02}',
                      'unit': 'W', 'state': str(index)} for index in range(20)]}))
    await page.locator('#settings-button').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    await page.locator('[data-settings-category=sources]').click()
    power = page.get_by_role('combobox', name='Actual power', exact=True)
    await power.fill('')
    await power.press('ArrowUp')
    await expect(page.get_by_role('listbox').get_by_role('option').last).to_have_attribute('aria-selected', 'true')
    await expect(power).to_be_focused()
    await expect(power).to_have_value('')
    geometry = await page.evaluate('''() => {
        const menu = document.querySelector('.sensor-suggestions');
        const rect = node => { const {left, right, top, bottom, height} = node.getBoundingClientRect(); return {left, right, top, bottom, height}; };
        const style = getComputedStyle(menu);
        return {menu: rect(menu), option: rect(menu.querySelector('[aria-selected=true]')),
            content: rect(document.querySelector('#content-scroll')),
            input: rect(document.querySelector('[name=actual_power_entity]')), dock: rect(document.querySelector('#settings-actions')),
            viewport: {width: innerWidth, height: innerHeight}, scrollWidth: document.documentElement.scrollWidth,
            background: style.backgroundColor, expectedBackground: getComputedStyle(document.documentElement).getPropertyValue('--pv-raised').trim(),
            containerType: getComputedStyle(document.querySelector('#settings-scroll')).containerType,
            parent: menu.parentElement.tagName};
    }''')
    assert geometry['parent'] == 'BODY'
    assert geometry['containerType'] == 'size'
    assert geometry['menu']['left'] >= 0
    assert geometry['menu']['right'] <= width
    assert geometry['menu']['top'] >= geometry['content']['top']
    assert geometry['menu']['bottom'] <= geometry['content']['bottom']
    assert geometry['menu']['bottom'] <= min(height, geometry['dock']['top']) - 3
    assert geometry['menu']['height'] <= 242
    assert geometry['option']['top'] >= geometry['menu']['top']
    assert geometry['option']['bottom'] <= geometry['menu']['bottom']
    assert geometry['scrollWidth'] <= width
    artifacts = Path(os.getenv('PVYL_SENSOR_ARTIFACTS', 'artifacts/task-2-sensors'))
    artifacts.mkdir(parents=True, exist_ok=True)
    stem = f'sensors-{width}x{height}-{theme}'
    (artifacts / f'{stem}.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    await page.screenshot(path=str(artifacts / f'{stem}.png'))
    await power.press('Escape')
    await expect(page.get_by_role('listbox')).not_to_be_visible()
    assert errors == []


@pytest.fixture
async def browser_workspace(tmp_path, request):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    if getattr(request, 'param', True):
        await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=1))
    async with fake_server() as ha_url:
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url, ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(locale='en-US', http_credentials={'username': 'admin', 'password': 'browser-test'})
            page = await context.new_page()
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await expect(page.locator('main')).to_have_attribute('data-configuration-ready', 'true')
            await expect(page.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
            yield page, service, web
            assert errors == []
            await browser.close()
    service.store.close()


async def test_cancel_settings_reloads_persisted_configuration(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await service.configure(service.monitoring_settings.model_copy(update={'total_max_power_at_stc_w': 6200}))
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await page.locator('#ha-token').fill('replacement-token')
    async with page.expect_response(lambda r: r.request.method == 'GET' and r.url.endswith('/api/config')):
        await page.locator('#discard-settings-changes').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6200')
    await expect(page.locator('#ha-token')).to_have_value('')
    await expect(page.locator('#save-button')).to_be_disabled()
    await expect(page.locator('#settings-page')).to_be_visible()


async def test_cancel_settings_failure_preserves_draft(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await page.locator('#ha-token').fill('replacement-token')
    await page.route('**/api/config', lambda route: route.fulfill(status=502, json={'error': 'ha_connection_failed'}))
    async with page.expect_response(lambda r: r.request.method == 'GET' and r.url.endswith('/api/config')):
        await page.locator('#discard-settings-changes').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    await expect(page.locator('#ha-token')).to_have_value('replacement-token')
    await expect(page.locator('#save-button')).to_be_enabled()
    await expect(page.locator('#save-result')).to_contain_text('Cannot reach Home Assistant')


async def test_settings_loading_disables_edit_until_config_ready(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    requested = asyncio.Event()
    ready = asyncio.Event()
    requests = []

    async def configuration(route):
        requests.append(route.request.method)
        response = await route.fetch()
        requested.set()
        await ready.wait()
        await route.fulfill(response=response)

    await page.route('**/api/config', configuration)
    await page.reload(wait_until='domcontentloaded')
    await asyncio.wait_for(requested.wait(), 5)
    await page.locator('#settings-button').click()
    for selector in ['[name=total_max_power_at_stc_w]', '#ha-url', '#ha-token', '#load-entities', '#save-button', '#discard-settings-changes']:
        await expect(page.locator(selector)).to_be_disabled()
    for selector in ['#live-tab', '#history-tab', '#forecast-tab', '#settings-button']:
        await expect(page.locator(selector)).to_be_disabled()
    await expect(page.locator('.brand')).to_have_attribute('aria-disabled', 'true')
    await page.locator('.brand').evaluate('node => node.click()')
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#theme-select')).to_be_enabled()
    await expect(page.locator('#language-select')).to_be_enabled()
    assert requests == ['GET']
    ready.set()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_enabled()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await expect(page.locator('#save-button')).to_be_disabled()
    await expect(page.locator('#live-tab')).to_be_enabled()


async def test_saving_settings_blocks_dependent_navigation(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    requested = asyncio.Event()
    ready = asyncio.Event()

    async def configuration(route):
        if route.request.method == 'PUT':
            requested.set()
            await ready.wait()
        await route.continue_()

    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await page.route('**/api/config', configuration)
    await page.locator('#save-button').click()
    await asyncio.wait_for(requested.wait(), 5)
    for selector in ['#live-tab', '#history-tab', '#forecast-tab', '#settings-button']:
        await expect(page.locator(selector)).to_be_disabled()
    await page.locator('.brand').evaluate('node => node.click()')
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('dialog')).not_to_be_visible()
    await expect(page.locator('#theme-select')).to_be_enabled()
    await expect(page.locator('#language-select')).to_be_enabled()
    ready.set()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.monitoring_settings.total_max_power_at_stc_w == 6100
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('dialog')).not_to_be_visible()


async def test_settings_forecast_geometry_bounds_and_numeric_equivalence(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await page.locator('[name=total_max_power_at_stc_w]').fill('5000.0')
    await expect(page.locator('#save-button')).to_be_disabled()
    await page.locator('[name=total_max_power_at_stc_w]').fill('')
    await expect(page.locator('#save-button')).to_be_enabled()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_focused()
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    await page.locator('[name=total_max_power_at_stc_w]').fill('5000')
    await page.locator('[data-settings-category=forecast]').click()
    await page.locator('[name=forecast_enabled]').check()
    await page.locator('[name=forecast_tilt_deg]').fill('90')
    await page.locator('#forecast-direction').select_option('custom')
    await page.locator('[name=forecast_azimuth_deg]').fill('360')
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_be_focused()
    await page.locator('[name=forecast_azimuth_deg]').fill('359.9')
    await page.locator('[name=forecast_noct_c]').fill('20')
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_be_focused()
    await page.locator('[name=forecast_noct_c]').fill('45')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.tilt_deg == 90
    assert service.forecast.settings.azimuth_deg == 359.9


@pytest.mark.parametrize('superseded_result', ['success', 'error'])
async def test_history_rejects_superseded_range_responses(browser_workspace, superseded_result, monkeypatch):
    from types import SimpleNamespace
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module
    from urllib.parse import parse_qs, urlsplit
    from playwright.async_api import expect
    from test_engine import samples
    from pvyieldlens.engine import calculate

    page, service, _ = browser_workspace
    first = service.store.cursor
    recent = first + 2*86400
    for start, end, power in [(first, first+60, 2000), (first+60, recent, None), (recent, recent+60, 1000)]:
        service.store.settle(calculate(service.monitoring_settings, samples(power=power, at=start) if power is not None else [],
                                      start, end), 1, 'UTC')
    clock = SimpleNamespace(time=lambda: recent+120)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    await page.evaluate('now => Date.now = () => now', (recent+120)*1000)
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-energy')).to_have_text('0.062')
    await page.locator('#history-range [data-value="7d"]').click()
    await expect(page.locator('#history-energy')).to_have_text('0.124')

    older_requested = asyncio.Event()
    release_older = asyncio.Event()
    older_completed = asyncio.Event()

    async def history(route):
        query = parse_qs(urlsplit(route.request.url).query)
        period = query['period'][0]
        response = await route.fetch()
        if period == '30d':
            older_requested.set()
            await release_older.wait()
            if superseded_result == 'error':
                await route.fulfill(status=502, json={'error': 'invalid_time_range'})
            else:
                await route.fulfill(response=response)
            older_completed.set()
        else:
            await route.fulfill(response=response)

    await page.route('**/api/history?*', history)
    await page.locator('#history-range [data-value="30d"]').click()
    await asyncio.wait_for(older_requested.wait(), timeout=5)
    await page.locator('#history-range [data-value="24h"]').click()
    await expect(page.locator('#history-energy')).to_have_text('0.062')
    release_older.set()
    await asyncio.wait_for(older_completed.wait(), timeout=5)
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    assert await page.locator('#history-range [data-value="24h"]').get_attribute('aria-pressed') == 'true'
    assert await page.locator('#history-energy').inner_text() == '0.062'
    assert await page.locator('#history-page .banner').count() == 0
    await page.locator('#history-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#history-chart .chart-tooltip')).to_contain_text('1,000 W')
    await page.keyboard.press('ArrowLeft')
    await expect(page.locator('#history-chart .chart-tooltip')).to_contain_text('1,000 W')


async def test_rolling_history_refreshes_only_when_complete_window_membership_changes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module
    from playwright.async_api import async_playwright, expect
    from test_engine import samples, settings
    from test_integration import fake_server
    from pvyieldlens.engine import calculate
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    now = int(time.time())
    clock = SimpleNamespace(time=lambda: now)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    start = now - 86400
    config = settings(settlement_interval_minutes=1, update_interval_seconds=1)
    await service.configure(config, now=start)
    for offset, power in [(0, 1000), (60, 2000), (120, 3000)]:
        service.store.settle(calculate(config, samples(power=power, at=start+offset),
                                      start+offset, start+offset+60), 1, 'UTC')
    service._mark_offline()
    web = create_app(service, Runtime(web_password='browser-test'), run_background=False)
    async with fake_server(web) as url, async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(http_credentials={'username':'admin','password':'browser-test'})
        await page.add_init_script(f'window.testNow = {now * 1000}; Date.now = () => window.testNow;')
        history_requests = []
        errors = []
        page.on('request', lambda request: history_requests.append(request.url) if '/api/history?' in request.url else None)
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def advance_clock(seconds):
            clock.time = lambda: now+seconds
            await page.evaluate('now => { window.testNow = now; }', (now+seconds)*1000)
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass

        await page.goto(url)
        await expect(page.locator('main')).to_have_attribute('data-configuration-ready', 'true')
        await expect(page.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
        # Wait for the initial snapshot to seed the history latest_settled_window key.
        async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
            pass
        await page.locator('#history-tab').click()
        await page.locator('#history-range [data-value="24h"]').click()
        await expect(page.locator('#history-chart svg')).to_be_visible()
        charts = page.locator('#history-chart svg, #pr-chart svg')
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'initial')")
        await page.locator('#history-chart .chart-hit-area').focus()
        await page.keyboard.press('ArrowRight')
        await expect(page.locator('#history-chart .chart-tooltip')).to_contain_text('1,000 W')
        initial_requests = len(history_requests)
        await advance_clock(0)
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['initial', 'initial']
        assert len(history_requests) == initial_requests

        # A straddling window is excluded from both the summary and chart.
        await advance_clock(90)
        await expect(charts.first).not_to_have_attribute('data-original', 'initial')
        await expect(page.locator('#history-chart .chart-tooltip')).to_be_hidden()
        for selector in ['#history-chart', '#pr-chart']:
            await page.locator(selector + ' .chart-hit-area').focus()
            await page.keyboard.press('ArrowRight')
            await expect(page.locator(selector + ' .chart-tooltip')).to_contain_text('3,000 W')
            await page.keyboard.press('ArrowLeft')
            await expect(page.locator(selector + ' .chart-tooltip')).to_contain_text('3,000 W')
        assert len(history_requests) == initial_requests + 1
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'remaining')")
        await advance_clock(100)
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['remaining', 'remaining']

        # A window ending exactly at the rolling start no longer overlaps the range.
        await advance_clock(180)
        await expect(charts).to_have_count(0)
        empty = page.locator('#history-chart .chart-empty, #pr-chart .chart-empty')
        await expect(empty).to_have_count(2)
        await empty.evaluate_all("nodes => nodes.forEach(node => node.dataset.original = 'empty')")
        await advance_clock(210)
        assert await empty.evaluate_all('nodes => nodes.map(node => node.dataset.original)') == ['empty', 'empty']
        assert len(history_requests) == initial_requests + 2

        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#history-range [data-value="7d"]').click()
        await page.locator('#history-aggregation [data-value=settlement]').click()
        await expect(charts).to_have_count(2)
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'hidden')")
        await page.locator('#settings-button').click()
        await advance_clock(7*86400+180)
        assert len(history_requests) == initial_requests+3
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['hidden', 'hidden']
        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#history-tab').click()
        await expect(charts).to_have_count(0)
        assert len(history_requests) == initial_requests+4
        assert errors == []
        await browser.close()
    service.store.close()

@pytest.mark.parametrize(('mode', 'edited_connection'), [('app', False), ('docker', False), ('docker', True)])
async def test_settings_discovers_once_and_preserves_edits(browser_workspace, mode, edited_connection):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    configuration_reads = []
    requests = []
    discovery_ready = asyncio.Event()

    async def configuration(route):
        configuration_reads.append(route.request.method)
        response = await route.fetch()
        body = await response.json()
        body['mode'] = mode
        await route.fulfill(response=response, json=body)

    async def discovery(route):
        requests.append(route.request.post_data_json)
        await discovery_ready.wait()
        await route.continue_()

    await page.route('**/api/config', configuration)
    await page.route('**/api/connection', discovery)
    assert requests == []
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_enabled()
    await expect(page.locator('#load-entities')).to_be_disabled()
    ha_url = await page.locator('#ha-url').input_value()
    await page.locator('[data-settings-category=sources]').click()
    await page.locator('[name=actual_power_entity]').fill('sensor.typed_power')
    await page.locator('[data-settings-category=modules]').click()
    await page.locator('[name=pmax_temperature_coefficient_pct_per_c]').fill('-0.4')
    if edited_connection:
        await page.locator('[data-settings-category=connection]').click()
        await page.locator('#ha-url').fill(ha_url + '/')
        await page.locator('#ha-token').fill('simulation-token')
    unsaved = await page.locator('#settings-form').evaluate('form => [...new FormData(form)]')
    await page.locator('#settings-button').click()
    await page.locator('#language-select').select_option('fr')
    await page.locator('#theme-select').select_option('dark')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    assert configuration_reads == ['GET']
    assert requests == [None if mode == 'app' else {'url': ha_url, 'token': ''}]
    assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
    discovery_ready.set()
    await expect(page.locator('#load-entities')).to_be_enabled()
    if edited_connection:
        await assert_sensor_candidates(page, 'actual_power', [])
        async with page.expect_response(lambda response: response.url.endswith('/api/connection')):
            await page.locator('#load-entities').click()
    for role, entity in [('actual_power', 'sensor.power'), ('module_temperature', 'sensor.temp'), ('irradiance', 'sensor.sun')]:
        await assert_sensor_candidates(page, role, [entity])
    await page.locator('#settings-button').click()
    await page.locator('#language-select').select_option('en')
    assert len(requests) == (2 if edited_connection else 1)
    assert configuration_reads == ['GET']
    assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
    await page.locator('[data-settings-category=connection]').click()
    if mode == 'docker':
        await page.locator('#ha-url').fill(ha_url + '/')
        await page.locator('#ha-token').fill('simulation-token')
    async with page.expect_response(lambda response: response.url.endswith('/api/connection')):
        await page.locator('#load-entities').click()
    assert requests[-1] == (None if mode == 'app' else {'url': ha_url + '/', 'token': 'simulation-token'})
    assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
    await expect(page.locator('[name=actual_power_entity]')).to_have_value('sensor.typed_power')
    await expect(page.locator('[name=pmax_temperature_coefficient_pct_per_c]')).to_have_value('-0.4')


async def test_cancel_settings_retires_temporary_connection_candidates(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])
    saved_url = await page.locator('#ha-url').input_value()
    await page.route('**/api/connection', lambda route: route.fulfill(json={
        'home_timezone': 'Europe/Paris', 'location': None,
        'entities': [{'entity_id': 'sensor.preview_power', 'name': 'Preview power', 'unit': 'W', 'state': '2'},
                     {'entity_id': 'sensor.pvyieldlens_output', 'name': 'Feedback', 'unit': 'W', 'state': '3'}]}))
    await page.locator('#ha-url').fill('http://preview.invalid:8123')
    await page.locator('#ha-token').fill('preview-token')
    await assert_sensor_candidates(page, 'actual_power', [])
    await page.locator('#load-entities').click()
    await assert_sensor_candidates(page, 'actual_power', ['sensor.preview_power'])
    await page.locator('#discard-settings-changes').click()
    await expect(page.locator('#ha-url')).to_have_value(saved_url)
    await expect(page.locator('#ha-token')).to_have_value('')
    await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])
    await expect(page.locator('#save-button')).to_be_disabled()
    await page.locator('#live-tab').click()
    await page.locator('#settings-button').click()
    await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])


@pytest.mark.parametrize('change_url', [False, True])
async def test_settings_saving_new_credentials_retires_old_candidates(browser_workspace, change_url):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.locator('#settings-button').click()
    await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])
    saved_url = await page.locator('#ha-url').input_value()
    if change_url:
        await page.locator('#ha-url').fill('http://preview.invalid:8123')
    await page.locator('#ha-token').fill('replacement-token')
    await assert_sensor_candidates(page, 'actual_power', [])
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    await assert_sensor_candidates(page, 'actual_power', [])
    if change_url:
        await page.locator('#ha-url').fill(saved_url)
        await assert_sensor_candidates(page, 'actual_power', [])


@pytest.mark.parametrize('saved_credentials', [False, True])
async def test_settings_first_connection_failure_keeps_polling_and_allows_retry(tmp_path, saved_credentials):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        await service.configure(settings(update_interval_seconds=1))
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token' if saved_credentials else ''), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US',
                                          http_credentials={'username':'admin', 'password':'browser-test'})
            fail_ready = asyncio.Event()
            requests = []

            async def discovery(route):
                requests.append(route.request.post_data_json)
                if len(requests) == 1:
                    await fail_ready.wait()
                    await route.fulfill(status=502, json={'error':'ha_connection_failed'})
                else:
                    await route.continue_()

            await page.route('**/api/connection', discovery)
            await page.goto(url)
            await page.locator('#settings-button').click()
            await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            if not saved_credentials:
                assert requests == []
                await assert_sensor_candidates(page, 'actual_power', [])
                await page.locator('#ha-url').fill(ha_url)
                await page.locator('#ha-token').fill('simulation-token')
                await page.locator('#load-entities').click()
            await expect(page.locator('#load-entities')).to_be_disabled()
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert requests == [{'url':ha_url, 'token':'' if saved_credentials else 'simulation-token'}]
            fail_ready.set()
            await expect(page.locator('#connection-result')).to_contain_text('Cannot reach Home Assistant')
            await expect(page.locator('#load-entities')).to_be_enabled()
            await assert_sensor_candidates(page, 'actual_power', [])
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            async with page.expect_response(lambda response: response.url.endswith('/api/connection')):
                await page.locator('#load-entities').click()
            await assert_sensor_candidates(page, 'actual_power', ['sensor.power'])
            assert requests == [{'url':ha_url, 'token':'' if saved_credentials else 'simulation-token'}] * 2
            await expect(page.locator('#ha-url')).to_have_value(ha_url)
            await expect(page.locator('#ha-token')).to_have_value('' if saved_credentials else 'simulation-token')
            await browser.close()
        service.store.close()


@pytest.mark.parametrize('initial_location', [False, True])
async def test_settings_refreshes_active_location_without_changing_drafts(browser_workspace, initial_location):
    from playwright.async_api import expect
    from pvyieldlens.settings import HALocation
    from test_integration import fake_server

    page, service, _ = browser_workspace
    response = await page.request.get(page.url + 'api/config')
    await service.configure(service.monitoring_settings, origin=(await response.json())['connection']['url'])
    location = HALocation(origin=service.origin, latitude=1.0, longitude=2.0, location_name='Active', home_timezone='UTC')
    if initial_location:
        service.forecast.configure(service.monitoring_settings, service.forecast.settings, service.origin, location)
    await page.reload()
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('#forecast-location')).to_have_text('Active · 1, 2' if initial_location else 'HA location is not available yet.')
    await page.locator('[name=forecast_noct_c]').fill('48')
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    async with fake_server() as preview_url:
        await page.locator('button[data-settings-category=connection]').click()
        await expect(page.locator('#load-entities')).to_be_enabled()
        await page.locator('#ha-url').fill(preview_url)
        await page.locator('#ha-token').fill('simulation-token')
        await page.locator('#load-entities').click()
        await expect(page.locator('#connection-result')).to_have_text('Connection verified')
        await page.locator('button[data-settings-category=forecast]').click()
        await expect(page.locator('#forecast-location')).to_have_text('Active · 1, 2' if initial_location else 'HA location is not available yet.')
        drafts = await page.locator('#settings-form').evaluate('form => [...new FormData(form)]')
        for current, expected in (
            (location, 'Active · 1, 2'),
            (location.model_copy(update={'location_name': 'Renamed'}), 'Renamed · 1, 2'),
            (location.model_copy(update={'latitude': -33.86, 'longitude': 151.21, 'home_timezone': 'Australia/Sydney'}),
             'Active · -33.86, 151.21'),
            (None, 'HA location is not available yet.'),
        ):
            service.forecast.configure(service.monitoring_settings, service.forecast.settings, service.origin, current)
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            await expect(page.locator('#forecast-location')).to_have_text(expected)
            assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == drafts
            await expect(page.locator('#ha-url')).to_have_value(preview_url)
            await expect(page.locator('#ha-token')).to_have_value('simulation-token')
            await expect(page.locator('#save-button')).to_be_enabled()
            await page.locator('#settings-button').click()
            await expect(page.locator('#forecast-location')).to_have_text(expected)
        assert service.forecast.settings.enabled is False


@pytest.mark.parametrize('change', ['forecast', 'monitoring', 'connection'])
@pytest.mark.parametrize('browser_workspace', [False], indirect=True)
async def test_live_curve_save_resets_only_for_monitoring_changes(browser_workspace, change):
    import re
    from datetime import datetime, timezone
    from playwright.async_api import expect
    from test_engine import samples, settings

    page, service, _ = browser_workspace
    response = await page.request.get(page.url + 'api/config')
    connection = (await response.json())['connection']
    now = int(time.time())
    await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=1, home_timezone='Asia/Shanghai'),
                            now=now-900, origin=connection['url'])
    service.store.add_observations(samples(at=now-660), origin=service.origin)
    await service.tick(now)
    await page.clock.set_fixed_time(datetime.fromtimestamp(now, timezone.utc))
    await page.reload()
    await expect(page.locator('main')).to_have_attribute('data-configuration-ready', 'true')
    await expect(page.locator('#live-actual')).to_have_text('3,348')
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile('C'))
    curve = await page.locator('#live-chart path.series').first.get_attribute('d')
    seeds = []
    page.on('request', lambda request: seeds.append(request.url) if request.url.endswith('/api/live-series') else None)
    await page.locator('#settings-button').click()
    if change == 'forecast':
        await page.locator('button[data-settings-category=forecast]').click()
        await page.locator('[name=forecast_noct_c]').fill('48')
        # A normalized URL and explicit identical credential still mean the same connection.
        await page.locator('button[data-settings-category=connection]').click()
        await page.locator('#ha-url').fill(connection['url'] + '/')
        await page.locator('#ha-token').fill('simulation-token')
    elif change == 'monitoring':
        await page.locator('button[data-settings-category=modules]').click()
        await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    else:
        await page.locator('button[data-settings-category=connection]').click()
        await page.locator('#ha-token').fill('replacement-token')
    if change == 'forecast':
        await page.locator('#save-button').click()
    else:
        async with page.expect_response(lambda response: response.url.endswith('/api/live-series')):
            await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    await expect(page.locator('#ha-token')).to_have_value('')
    await page.locator('#live-tab').click()
    if change == 'forecast':
        await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', curve)
        assert seeds == []
    elif change == 'monitoring':
        await expect(page.locator('#live-chart path.series').first).not_to_have_attribute('d', re.compile('C'))
        assert len(seeds) == 1
    else:
        # Re-authenticating the same HA origin reloads its compatible stored observations.
        assert len(seeds) == 1
        await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile('C'))


async def test_settings_pr_history_days_preserves_draft_and_reveals_validation(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    response = await page.request.get(page.url + 'api/config')
    connection = (await response.json())['connection']
    await service.configure(service.monitoring_settings.model_copy(update={'home_timezone': 'Asia/Shanghai'}),
                            origin=connection['url'])
    await page.reload()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    control = page.locator('[name=forecast_pr_history_days]')
    await expect(control).to_have_value('14')
    for value in ('', '2', '91', '3.5'):
        await control.fill(value)
        await page.locator('button[data-settings-category=modules]').click()
        await page.locator('#save-button').click()
        await expect(control).to_be_focused()
        await expect(control).to_have_value(value)
        assert service.forecast.settings.pr_history_days == 14
    revision, live = service.store.revision, service.live_window
    await control.fill('30')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.pr_history_days == 30
    assert (service.store.revision, service.live_window) == (revision, live)
    await page.reload()
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(control).to_have_value('30')
    await page.route('**/api/config', lambda route: route.fulfill(status=422, json={
        'error': 'invalid_configuration', 'fields': ['forecast_settings.pr_history_days']}))
    await control.fill('31')
    await page.locator('button[data-settings-category=modules]').click()
    await page.locator('#save-button').click()
    await expect(control).to_be_focused()
    await expect(control).to_have_attribute('aria-invalid', 'true')
    await expect(control).to_have_value('31')
