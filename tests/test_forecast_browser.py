import copy
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_browser import browser_workspace

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')


def forecast_payload(day='2026-11-01', home_timezone='UTC'):
    zone = ZoneInfo(home_timezone)
    dates = [datetime.fromisoformat(day).replace(tzinfo=zone) + timedelta(days=i) for i in range(8)]
    boundaries = [date.timestamp() for date in dates]
    def total(start, end):
        return {'start': start, 'end': end, 'forecast_energy_kwh': 3720 * (end-start) / 3600000,
                'corrected_forecast_energy_kwh': 3348 * (end-start) / 3600000, 'data_completeness_percent': 100, 'quality': 'complete'}
    rows = []
    start = boundaries[0] // 900 * 900
    while start < boundaries[-1]:
        left, right = max(start, boundaries[0]), min(start + 900, boundaries[-1])
        rows.append({'start': left, 'end': right, 'irradiance_w_m2': 800, 'air_temperature_c': 20,
                     'cell_temperature_c': 45, 'forecast_power_w': 3720, 'corrected_forecast_power_w': 3348,
                     'corrected_forecast_energy_kwh': 3348 * (right-left) / 3600000, 'forecast_energy_kwh': 3720 * (right-left) / 3600000,
                     'quality': 'complete'})
        start += 900
    return {'correction': {'pr': 90, 'history_days': 14, 'start': boundaries[0]-14*86400, 'end': boundaries[0]},
            'status': 'ready', 'refreshing': False, 'fetched_at': boundaries[0] + 3600,
            'calculated_at': boundaries[0] + 48000, 'last_error': None, 'home_timezone': home_timezone,
            'geometry': None, 'unavailable_angles': [],
            'today': total(boundaries[0], boundaries[1]),
            'remaining_today': {**total(boundaries[0]+48000, boundaries[1]), 'forecast_energy_kwh': 39.68, 'corrected_forecast_energy_kwh': 35.712},
            'tomorrow': total(boundaries[1], boundaries[2]),
            'seven_days': {**total(boundaries[0], boundaries[-1]), 'forecast_energy_kwh': 624.96, 'corrected_forecast_energy_kwh': 562.464},
            'days': [{**total(left, right), 'day': dates[i].date().isoformat(),
                      'weather': {'weather_code': [0, 3, 61, 71, 95, None, 48][i],
                                  'air_temperature_min_c': 0 if i == 0 else 10 + i,
                                  'air_temperature_max_c': 20 + i,
                                  'quality': 'partial' if i == 5 else 'complete'}}
                     for i, (left, right) in enumerate(zip(boundaries, boundaries[1:]))], 'intervals': rows}


@pytest.fixture
async def forecast_page(browser_workspace):
    page, service, web = browser_workspace
    state = {'view': forecast_payload(), 'hourly': 0, 'refresh': 0}
    async def full(route):
        state['hourly'] += 1
        await route.fulfill(json=state['view'])
    async def light(route):
        payload = service.snapshot()
        payload['forecast'] = {key: value for key, value in state.get('light', state['view']).items() if key not in ('days', 'intervals')}
        await route.fulfill(json=payload)
    async def refresh(route):
        state['refresh'] += 1
        state['view']['refreshing'] = True
        await route.fulfill(status=202, json={'scheduled': True, 'status': state['view']['status']})
    await page.route('**/api/forecast', full)
    await page.route('**/api/snapshot', light)
    await page.route('**/api/forecast/refresh', refresh)
    await page.evaluate('now => Date.now = () => now', state['view']['calculated_at'] * 1000)
    return page, state, web


@pytest.mark.parametrize('theme', ['light', 'dark'])
async def test_remaining_today_uses_the_primary_card_style(forecast_page, theme):
    from playwright.async_api import expect

    page, _, _ = forecast_page
    await page.locator('#theme-select').select_option(theme)
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-remaining')).to_have_text('39.68')
    await expect(page.locator('html')).to_have_attribute('data-theme', theme)

    dashboard, ordinary, efficiency, remaining, tomorrow = await page.locator(
        '.live-metrics > .metric:nth-child(-n+2), .history-metrics > .metric:first-child, .forecast-metrics > .metric'
    ).evaluate_all('''cards => cards.map(card => {
        const { backgroundColor, borderTopColor } = getComputedStyle(card);
        return [backgroundColor, borderTopColor];
    })''')
    assert remaining == dashboard == efficiency
    assert tomorrow == ordinary
    assert remaining != tomorrow

    accent = await page.locator('#forecast-tab').evaluate('tab => getComputedStyle(tab).color')
    for value in ('#live-actual', '#history-pr'):
        await expect(page.locator(value)).to_have_css('color', accent)

    chart_series = page.locator('#forecast-chart path.series')
    await expect(chart_series).to_have_count(2)
    series_colors = await chart_series.evaluate_all('paths => paths.map(path => getComputedStyle(path).stroke)')
    card_colors = await page.locator(
        '.forecast-metrics .forecast-pair strong'
    ).evaluate_all('values => values.map(value => getComputedStyle(value).color)')
    assert series_colors[0] != series_colors[1]
    assert card_colors == series_colors * 2


async def test_forecast_days_select_quarter_hour_details_and_preserve_selection(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    chart = page.locator('#forecast-chart')
    heading = page.locator('#forecast-day-heading')
    marker = chart.locator('.current-time')
    marker_help = page.locator('#forecast-marker-help')
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await expect(heading).to_have_text('Today')
    # A vertical SVG line has a zero-width bounding box even when its stroke is painted.
    await expect(marker).to_have_css('display', 'inline')
    await expect(marker_help).to_be_visible()
    await expect(page.locator('#forecast-remaining')).to_have_text('39.68')
    await expect(page.locator('#forecast-tomorrow')).to_have_text('89.28')
    await expect(page.locator('#forecast-seven-days')).to_contain_text('624.96')
    await page.locator('#forecast-days button').nth(2).focus()
    await page.keyboard.press('Enter')
    await expect(heading).to_have_text('Nov 3')
    assert await marker.count() == 0
    await expect(marker_help).to_have_count(0)
    await expect(page.locator('#forecast-day-total')).to_have_text('89.28 kWh')
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr')).to_have_count(96)
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('3,720')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('0.93')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('800')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('20')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('45')
    await expect(page.locator('#forecast-details th')).to_contain_text([
        'Interval', 'Irradiance', 'Air temperature', 'Estimated cell temperature', 'Original forecast power', 'Corrected forecast power', 'Original forecast energy', 'Corrected forecast energy'])
    await expect(chart.locator('svg')).to_have_attribute('aria-label', 'Original forecast power / Corrected forecast power')
    await chart.locator('.chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0.93 kWh')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('3,720 W')
    await expect(page.locator('#forecast-fetched')).to_contain_text('Nov 1')
    await page.locator('#settings-button').click()
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button').nth(2)).to_have_attribute('aria-pressed', 'true')
    await page.locator('#forecast-days button').first.click()
    await expect(heading).to_have_text('Today')
    await expect(marker).to_have_css('display', 'inline')
    await expect(marker_help).to_be_visible()
    await page.locator('#forecast-refresh').click()
    await expect(page.locator('#forecast-refresh')).to_be_disabled()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-page')).to_be_visible()
    assert state['refresh'] == 1


@pytest.mark.parametrize(('status', 'failed_angle'), [
    ('configuration_required', False), ('location_unavailable', False), ('unavailable', False), ('unavailable', True),
    ('loading', False), ('partial', False), ('stale', False), ('stale', True),
])
async def test_forecast_states_are_truthful(forecast_page, status, failed_angle):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    view = state['view']
    view['status'] = status
    if status in ('configuration_required', 'location_unavailable', 'unavailable', 'loading'):
        view.update(fetched_at=None, days=[], intervals=[], today=None, remaining_today=None, tomorrow=None, seven_days=None)
    if status in ('partial', 'stale'):
        view['days'][1].update(forecast_energy_kwh=None, corrected_forecast_energy_kwh=None, quality='partial', data_completeness_percent=50)
        view['seven_days'].update(forecast_energy_kwh=None, corrected_forecast_energy_kwh=None, quality='partial', data_completeness_percent=92.85)
        view['tomorrow'] = view['days'][1]
        view['intervals'][144].update(forecast_power_w=None, corrected_forecast_power_w=None,
                                      forecast_energy_kwh=None, corrected_forecast_energy_kwh=None, quality='unavailable')
    issues = [{'axis': 'tilt', 'entity_id': 'sensor.tracker_tilt'}]
    if status == 'unavailable':
        if failed_angle:
            view.update(last_error='forecast_angle_unavailable', unavailable_angles=issues)
        else:
            view['last_error'] = 'forecast_fetch_failed'
    if status == 'stale':
        if failed_angle:
            clock = await page.context.new_cdp_session(page)
            await clock.send('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Tokyo'})
            view.update(status='partial', geometry={'tilt_deg': 28.4, 'azimuth_deg': 180,
                                                   'read_at': view['fetched_at'] - 33*60})
        else:
            view['last_error'] = 'forecast_fetch_failed'
    await page.locator('#forecast-tab').click()
    if status in ('configuration_required', 'location_unavailable', 'loading') or status == 'unavailable' and not failed_angle:
        await expect(page.locator('#forecast-status')).to_have_attribute('data-status', status)
    else:
        await expect(page.locator('#forecast-status')).to_have_count(0)
    if status in ('partial', 'stale'):
        await expect(page.locator('#forecast-seven-days')).to_have_text('— kWh')
        await expect(page.locator('#forecast-days button').first).to_contain_text('89.28')
        await page.locator('#forecast-days button').nth(1).click()
        await expect(page.locator('#forecast-day-total')).to_have_text('— kWh')
        await expect(page.locator('#forecast-day-data-completeness')).to_have_count(0)
        content = (await page.locator('#forecast-page').inner_text()).lower()
        assert not any(word in content for word in ('completeness', 'quality', 'coverage', 'partial', 'stale'))
        for label in await page.locator('#forecast-days button').evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-label'))"):
            assert not any(word in label.lower() for word in ('complete', 'quality', 'coverage', 'partial'))
        assert await page.locator('#forecast-chart path.series').first.evaluate("node => (node.getAttribute('d').match(/M/g) || []).length") == 2
        geometry = await page.locator('#forecast-chart').evaluate('''host => {
            const path = host.querySelector('path.series'), width = host.clientWidth - 60;
            return {left: path.getPointAtLength(0).x,
                right: path.getPointAtLength(path.getTotalLength()).x,
                edge: host.clientWidth - 12, gapStart: 48 + width / 2, gapEnd: 48 + width * 49 / 96,
                samples: Array.from({length: 2001}, (_, index) => path.getPointAtLength(path.getTotalLength() * index / 2000).x)};
        }''')
        assert geometry['left'] == pytest.approx(48, abs=0.05)
        assert geometry['right'] == pytest.approx(geometry['edge'], abs=0.05)
        assert all(x <= geometry['gapStart'] + 0.05 or x >= geometry['gapEnd'] - 0.05 for x in geometry['samples'])
        await expect(page.locator('#forecast-fetched')).to_contain_text('Nov 1')
        if status == 'stale' and failed_angle:
            await expect(page.locator('#forecast-geometry')).to_contain_text('28.4°')
            await expect(page.locator('#forecast-geometry')).to_contain_text('180°')
            await expect(page.locator('#forecast-angle-read-at')).to_contain_text('09:27')
            await expect(page.locator('#forecast-fetched')).to_contain_text('10:00')
            await expect(page.locator('#forecast-error')).to_be_empty()
            state['light'] = {**view, 'status': 'stale', 'last_error': 'forecast_angle_unavailable',
                              'unavailable_angles': issues, 'calculated_at': view['calculated_at'] + 1}
            await expect(page.locator('#forecast-error')).to_contain_text('Module tilt')
            await expect(page.locator('#forecast-error')).to_contain_text('sensor.tracker_tilt')
            await expect(page.locator('#forecast-error')).to_contain_text('Showing the last forecast')
            await expect(page.locator('#forecast-angle-read-at')).to_contain_text('09:27')
            await expect(page.locator('#forecast-chart svg')).to_be_visible()
        elif status == 'stale':
            await expect(page.locator('#forecast-error')).to_contain_text('Weather refresh failed')
    else:
        await expect(page.locator('#forecast-remaining')).to_have_text('—')
        await expect(page.locator('#forecast-fetched')).to_contain_text('No successful fetch')
        if status == 'unavailable':
            await expect(page.locator('#forecast-tomorrow')).to_have_text('—')
            await expect(page.locator('#forecast-geometry')).to_have_count(0)
            await expect(page.locator('#forecast-refresh')).to_be_enabled()
            if failed_angle:
                await expect(page.locator('#forecast-error')).to_contain_text('Module tilt')
                await expect(page.locator('#forecast-error')).to_contain_text('sensor.tracker_tilt')
                await expect(page.locator('#forecast-error')).not_to_contain_text('Showing the last forecast')
                await expect(page.locator('#forecast-error')).not_to_contain_text('Weather refresh failed')
            else:
                await expect(page.locator('#forecast-status')).to_have_text('No usable weather forecast is available. Retry the refresh.')
                await expect(page.locator('#forecast-error')).to_contain_text('Weather refresh failed')
    if status in ('configuration_required', 'location_unavailable'):
        await expect(page.locator('#forecast-refresh')).to_be_disabled()
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#open-forecast-settings').click()
    category = 'modules' if status == 'configuration_required' else 'forecast'
    await expect(page.locator(f'[data-settings-category={category}]')).to_have_attribute('aria-current', 'location')


async def test_failed_manual_refresh_reports_request_error_with_cached_angle_notice(forecast_page):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    view = state['view']
    view.update(status='stale', last_error='forecast_angle_unavailable',
                geometry={'tilt_deg': 28.4, 'azimuth_deg': 180, 'read_at': view['fetched_at'] - 60},
                unavailable_angles=[{'axis': 'tilt', 'entity_id': 'sensor.tracker_tilt'}])
    await page.route('**/api/forecast/refresh', lambda route: route.fulfill(status=503, json={'error': 'error'}))
    await page.locator('#forecast-tab').click()
    notice = page.locator('#forecast-error')
    await expect(notice).to_contain_text('Showing the last forecast')
    await expect(notice).not_to_contain_text('Something went wrong')
    await page.locator('#forecast-refresh').click()
    await expect(notice).to_contain_text('Something went wrong. Please retry.')
    await expect(notice).to_contain_text('Module tilt (sensor.tracker_tilt)')
    await expect(notice).to_contain_text('Showing the last forecast')
    await expect(page.locator('#forecast-chart svg')).to_be_visible()
    await expect(page.locator('#forecast-refresh')).to_be_enabled()


async def test_scalar_poll_does_not_redraw_or_refetch_forecast_detail(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-chart svg')).to_be_visible()
    await page.locator('#forecast-chart svg').evaluate("node => node.dataset.original = 'steady'")
    marker = await page.locator('#forecast-chart .current-time').get_attribute('x1')
    requests = state['hourly']
    state['view']['remaining_today']['forecast_energy_kwh'] = 38.44
    state['view']['calculated_at'] += 1200
    await page.evaluate('now => Date.now = () => now', state['view']['calculated_at']*1000)
    await expect(page.locator('#forecast-remaining')).to_have_text('38.44')
    await expect(page.locator('#forecast-chart svg')).to_have_attribute('data-original', 'steady')
    await expect(page.locator('#forecast-days .day-weather').first).to_have_text('Clear sky')
    assert state['hourly'] == requests
    assert await page.locator('#forecast-chart .current-time').get_attribute('x1') != marker
    requests = state['hourly']
    async with page.expect_response('**/api/snapshot'):
        pass
    assert state['hourly'] == requests
    await page.locator('#settings-button').click()
    state['view']['fetched_at'] += 3600
    async with page.expect_response('**/api/snapshot'):
        pass
    assert state['hourly'] == requests
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-chart svg')).not_to_have_attribute('data-original', 'steady')
    assert state['hourly'] == requests + 1


async def test_forecast_midnight_refreshes_dates_without_changing_fetched_time(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    before_view = copy.deepcopy(state['view'])
    state['view'] = forecast_payload('2026-11-02')
    state['view']['fetched_at'] = before_view['fetched_at']
    await page.evaluate('now => Date.now = () => now', state['view']['calculated_at'] * 1000)
    await expect(page.locator('#forecast-days button').first).to_have_attribute('data-day', '2026-11-02')
    assert state['view']['fetched_at'] == before_view['fetched_at']
    assert state['view']['remaining_today']['forecast_energy_kwh'] >= 0
    await expect(page.locator('#forecast-days button').first).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('#forecast-days [aria-current=date]')).to_have_attribute('data-day', '2026-11-02')
    await expect(page.locator('#forecast-day-heading')).to_have_text('Today')
    await expect(page.locator('#forecast-chart .current-time')).to_have_css('display', 'inline')


@pytest.mark.parametrize('width', [320, 390])
async def test_forecast_ingress_mobile_and_language(forecast_page, width):
    from playwright.async_api import expect
    from fastapi import FastAPI
    from test_integration import fake_server
    page, state, web = forecast_page
    state['view'] = forecast_payload(home_timezone='America/New_York')
    ingress = FastAPI()
    ingress.mount('/api/hassio_ingress/forecast-test', web)
    async with fake_server(ingress) as url:
        await page.goto(url + '/api/hassio_ingress/forecast-test/')
        await expect(page.locator('main[data-configuration-ready=true][data-snapshot-ready=true]')).to_be_visible()
        await page.set_viewport_size({'width': width, 'height': 844})
        await page.locator('#forecast-tab').click()
        await expect(page.locator('#forecast-days button')).to_have_count(7)
        await page.locator('#forecast-details summary').click()
        await expect(page.locator('#forecast-rows tr')).to_have_count(100)
        rows = await page.locator('#forecast-rows').inner_text()
        assert 'GMT-4' in rows and 'GMT-5' in rows
        await expect(page.locator('#forecast-details-help')).to_be_visible()
        await expect(page.locator('#forecast-scroll-hint')).to_be_visible()
        geometry = await page.locator('#forecast-details').evaluate('''details => {
            const wrapper = details.querySelector('.table-scroll').getBoundingClientRect();
            const help = details.querySelector('#forecast-details-help').getBoundingClientRect();
            const numeric = details.querySelector('tbody td:nth-child(2)').getBoundingClientRect();
            return {right:wrapper.right, helpRight:help.right, numericRight:numeric.right};
        }''')
        assert geometry['helpRight'] <= geometry['right'] + 1
        assert geometry['numericRight'] <= geometry['right'] + 1
        await expect(page.locator('#forecast-rows time').first).to_have_attribute('datetime', '2026-11-01T04:00:00.000Z')
        await expect(page.locator('#forecast-rows time').first).to_have_attribute('aria-label', 'Nov 1, 2026, 00:00')
        await page.locator('#language-select').select_option('fr')
        await expect(page.locator('#forecast-chart svg')).to_have_attribute('aria-label', 'Puissance prévue originale / Puissance prévue corrigée')
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        for button in await page.locator('#forecast-days button').all():
            box = await button.bounding_box()
            assert box['width'] >= 44 and box['height'] >= 44


async def test_non_hour_timezone_clips_both_daily_interval_portions(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    state['view'] = forecast_payload(home_timezone='Asia/Kathmandu')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#forecast-days button').nth(1).click()
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr')).to_have_count(96)
    first, last = page.locator('#forecast-rows tr').first, page.locator('#forecast-rows tr').last
    await expect(first).to_contain_text('00:00')
    await expect(first).to_contain_text('00:15')
    await expect(first).to_contain_text('0.837')
    await expect(last).to_contain_text('23:45')
    await expect(last).to_contain_text('00:00')
    await expect(last).to_contain_text('0.93')
    await expect(page.locator('#forecast-day-total')).to_have_text('89.28 kWh')


async def test_shared_plot_keeps_gaps_and_readable_responsive_ticks(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    state['view']['intervals'][12].update(forecast_power_w=None, corrected_forecast_power_w=None,
                                         forecast_energy_kwh=None, corrected_forecast_energy_kwh=None, quality='unavailable')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-chart svg')).to_be_visible()
    result = await page.locator('#forecast-chart').evaluate("""host => {
        return {moves:host.querySelector('path').getAttribute('d').match(/M/g).length};
    }""")
    assert result['moves'] == 2
    await page.set_viewport_size({'width': 320, 'height': 844})
    await expect(page.locator('#forecast-chart svg')).to_be_visible()
    geometry = await page.locator('#forecast-chart').evaluate("""host => {
        return [...host.querySelectorAll('.time-tick')].map(node => {
          const {left,right} = node.getBoundingClientRect(); return {left,right};
        });
    }""")
    assert all(right['left'] >= left['right'] + 4 for left, right in zip(geometry, geometry[1:]))


async def test_forecast_refresh_and_rollover_keep_valid_selected_day(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#forecast-days button').nth(2).click()
    state['view'] = forecast_payload('2026-11-02')
    state['view']['fetched_at'] = 1793494800
    await expect(page.locator('#forecast-days button[data-day="2026-11-03"]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('#forecast-days button').first).to_have_attribute('data-day', '2026-11-02')
    requests = state['hourly']
    await page.locator('#forecast-refresh').click()
    async with page.expect_response('**/api/snapshot'):
        pass
    state['view']['refreshing'] = False
    state['view']['fetched_at'] += 3600
    await expect(page.locator('#forecast-refresh')).to_be_enabled()
    assert state['hourly'] == requests + 1
    await expect(page.locator('#forecast-days button[data-day="2026-11-03"]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#forecast-chart svg').evaluate("node => node.dataset.original = 'size'")
    await page.set_viewport_size({'width': 390, 'height': 844})
    await expect(page.locator('#forecast-chart svg')).not_to_have_attribute('data-original', 'size')
    await page.locator('#forecast-chart svg').evaluate("node => node.dataset.original = 'hidden'")
    await page.locator('#settings-button').click()
    await page.locator('#language-select').select_option('de')
    await page.set_viewport_size({'width': 320, 'height': 844})
    async with page.expect_response('**/api/snapshot'):
        pass
    await expect(page.locator('#forecast-chart svg')).to_have_attribute('data-original', 'hidden')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-chart svg')).not_to_have_attribute('data-original', 'hidden')


async def test_forecast_layout_evidence(forecast_page):
    from math import pi, sin
    from playwright.async_api import expect
    page, state, _ = forecast_page
    view = state['view']
    energies = [24.8, 29.1, 22.3, 19.5, 27.9, 30.4, 26.0]
    shape = [max(0, sin((slot / 4 + .125 - 6) / 12 * pi)) for slot in range(96)]
    for index, row in enumerate(view['intervals']):
        energy = shape[index % 96] / sum(shape) * energies[index // 96]
        row.update(forecast_power_w=energy * 4000, corrected_forecast_power_w=energy * 3600,
                   forecast_energy_kwh=energy, corrected_forecast_energy_kwh=energy * .9,
                   irradiance_w_m2=shape[index % 96] * 850,
                   air_temperature_c=15 + shape[index % 96] * 8,
                   cell_temperature_c=15 + shape[index % 96] * 33)
    for day, energy in zip(view['days'], energies):
        day.update(forecast_energy_kwh=energy, corrected_forecast_energy_kwh=energy * .9)
    view['today'] = view['days'][0]
    view['tomorrow'] = view['days'][1]
    remaining = sum(row['forecast_energy_kwh'] * max(0, row['end'] - max(row['start'], view['calculated_at'])) / (row['end']-row['start'])
                    for row in view['intervals'][:96] if row['end'] > view['calculated_at'])
    view['remaining_today'].update(forecast_energy_kwh=remaining, corrected_forecast_energy_kwh=remaining * .9)
    view['seven_days'].update(forecast_energy_kwh=sum(energies), corrected_forecast_energy_kwh=sum(energies) * .9)
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#language-select').select_option('zh')
    evidence = Path('artifacts/task-6-forecast')
    evidence.mkdir(parents=True, exist_ok=True)
    for size, width, height in [('desktop', 1440, 1100), ('mobile', 390, 1000)]:
        await page.set_viewport_size({'width': width, 'height': height})
        for theme in ('light', 'dark'):
            await page.locator('#theme-select').select_option(theme)
            await expect(page.locator('#forecast-chart path.series')).to_have_count(2)
            await page.locator('#content-scroll').evaluate('node => node.scrollTo(0, 0)')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            colors = await page.locator('#forecast-chart path.series').evaluate_all("nodes => nodes.map(node => getComputedStyle(node).stroke)")
            assert colors == (['rgb(184, 120, 36)', 'rgb(37, 133, 120)'] if theme == 'light'
                              else ['rgb(233, 181, 110)', 'rgb(113, 203, 185)'])
            await page.screenshot(path=str(evidence / f'forecast-{size}-{theme}.png'))
            await page.locator('#forecast-data > .panel').first.screenshot(path=str(evidence / f'forecast-calendar-{size}-{theme}.png'))
            await page.locator('#forecast-chart').scroll_into_view_if_needed()
            await page.locator('#forecast-chart .chart-hit-area').focus()
            for _ in range(43):
                await page.keyboard.press('ArrowRight')
            await expect(page.locator('#forecast-chart .chart-tooltip')).to_contain_text('修正预测电量')
            await page.locator('.forecast-hourly').screenshot(path=str(evidence / f'forecast-tooltip-{size}-{theme}.png'))
            await page.keyboard.press('Escape')
            await page.locator('#forecast-details summary').click()
            await expect(page.locator('#forecast-rows tr')).to_have_count(96)
            await page.locator('#forecast-details').evaluate("""details => {
                const scroll = document.querySelector('#content-scroll');
                scroll.scrollTo(0, scroll.scrollTop + details.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 16);
            }""")
            await page.screenshot(path=str(evidence / f'forecast-details-{size}-{theme}.png'))
            if size == 'mobile':
                await page.locator('#forecast-details .table-scroll').evaluate('node => node.scrollLeft = node.scrollWidth')
                await page.screenshot(path=str(evidence / f'forecast-details-corrected-{size}-{theme}.png'))
                await page.locator('#forecast-details .table-scroll').evaluate('node => node.scrollLeft = 0')
            await page.locator('#forecast-details summary').click()
    assert state['hourly'] == 1


async def test_new_batch_keeps_selected_date_with_an_older_light_snapshot(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#forecast-days button').nth(2).click()
    await page.locator('#settings-button').click()
    state['light'] = copy.deepcopy(state['view'])
    state['view']['fetched_at'] += 3600
    state['view']['calculated_at'] += 3600
    state['view']['remaining_today']['forecast_energy_kwh'] = 31.11
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-remaining')).to_have_text('31.11')
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await expect(page.locator('#forecast-days button[data-day="2026-11-03"]')).to_have_attribute('aria-pressed', 'true')
    requests = state['hourly']
    async with page.expect_response('**/api/snapshot'):
        pass
    assert state['hourly'] == requests
    await page.locator('#settings-button').click()
    state['view']['fetched_at'] += 3600
    state['view']['calculated_at'] += 3600
    del state['light']
    async with page.expect_response('**/api/snapshot'):
        pass
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button[data-day="2026-11-03"]')).to_have_attribute('aria-pressed', 'true')


async def test_weather_today_layout_in_six_languages_and_both_themes(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#forecast-days button').nth(2).click()
    evidence = Path('artifacts/task-5-weather')
    evidence.mkdir(parents=True, exist_ok=True)
    for width in (1440, 320):
        await page.set_viewport_size({'width': width, 'height': 1100})
        for language, today in [('en', 'Today'), ('zh', '今天'), ('de', 'Heute'), ('fr', 'Aujourd’hui'), ('it', 'Oggi'), ('pl', 'Dzisiaj')]:
            await page.locator('#language-select').select_option(language)
            for theme in ('light', 'dark'):
                await page.locator('#theme-select').select_option(theme)
                current = page.locator('#forecast-days [aria-current=date]')
                await expect(current.locator('.day-label')).to_have_text(today)
                await expect(current).to_have_attribute('data-day', '2026-11-01')
                await expect(current).to_have_attribute('aria-pressed', 'false')
                await expect(page.locator('#forecast-days [aria-pressed=true]')).to_have_attribute('data-day', '2026-11-03')
                await expect(current.locator('.day-temperature')).to_have_text('20° / 0°')
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                geometry = await page.locator('#forecast-days').evaluate('''host => ({
                    columns: getComputedStyle(host).gridTemplateColumns.split(' ').length,
                    cards: [...host.children].map(node => ({width: node.clientWidth, scroll: node.scrollWidth,
                        weather: node.querySelector('.day-weather').textContent}))})''')
                assert geometry['columns'] == (7 if width == 1440 else 4)
                assert all(card['scroll'] <= card['width'] and card['weather'] for card in geometry['cards']), (width, language, theme, geometry)
                if language == 'zh' and (width == 320 or theme == 'light'):
                    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0, 0)')
                    await page.screenshot(path=str(evidence / f'forecast-zh-{width}-{theme}.png'), full_page=True)
    assert state['hourly'] == 1


async def test_missing_daily_weather_keeps_energy_and_neutral_cards(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    state['view']['days'][0]['weather'] = None
    state['view']['days'][1]['weather'].update(weather_code=None, air_temperature_min_c=0, air_temperature_max_c=0)
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days .day-weather').first).to_have_text('Unknown weather')
    await expect(page.locator('#forecast-days .day-temperature').first).to_have_text('— / —')
    await expect(page.locator('#forecast-days .day-temperature').nth(1)).to_have_text('0° / 0°')
    await expect(page.locator('#forecast-day-total')).to_have_text('89.28 kWh')
    await expect(page.locator('#forecast-status')).to_have_count(0)


async def test_updates_corrected_detail_without_refetching_weather(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('[data-day="2026-11-03"]').click()
    fetched_at = state['view']['fetched_at']
    requests = state['hourly']
    state['view']['correction']['pr'] = 120
    for row in state['view']['intervals']:
        row.update(corrected_forecast_power_w=row['forecast_power_w'] * 1.2,
                   corrected_forecast_energy_kwh=row['forecast_energy_kwh'] * 1.2)
    for day in state['view']['days']:
        day['corrected_forecast_energy_kwh'] = day['forecast_energy_kwh'] * 1.2
    for key in ('today', 'remaining_today', 'tomorrow', 'seven_days'):
        state['view'][key]['corrected_forecast_energy_kwh'] = state['view'][key]['forecast_energy_kwh'] * 1.2
    state['view']['calculated_at'] += 1
    await expect(page.locator('#forecast-day-total-corrected')).to_have_text('107.136 kWh')
    await expect(page.locator('#forecast-days [aria-pressed=true]')).to_have_attribute('data-day', '2026-11-03')
    assert state['view']['fetched_at'] == fetched_at
    assert state['hourly'] == requests + 1
    assert state['refresh'] == 0
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('4,464')


@pytest.mark.parametrize(('day', 'count'), [('2026-03-29', 92), ('2026-10-25', 100)])
async def test_quarter_hour_dst_day_lengths(forecast_page, day, count):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    state['view'] = forecast_payload(day, 'Europe/Berlin')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr')).to_have_count(count)
    await expect(page.locator('#forecast-rows td').nth(7)).to_have_text('0.837')


@pytest.mark.parametrize('pr', [None, 0, 120])
async def test_missing_zero_and_above_100_correction_bars(forecast_page, pr):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    view = state['view']
    view['correction']['pr'] = pr
    for row in view['intervals']:
        row.update(corrected_forecast_power_w=None if pr is None else row['forecast_power_w'] * pr / 100,
                   corrected_forecast_energy_kwh=None if pr is None else row['forecast_energy_kwh'] * pr / 100)
    for total in [*view['days'], *(view[key] for key in ('today', 'remaining_today', 'tomorrow', 'seven_days'))]:
        total['corrected_forecast_energy_kwh'] = None if pr is None else total['forecast_energy_kwh'] * pr / 100
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await expect(page.locator('#forecast-remaining')).to_have_text('39.68')
    await expect(page.locator('#forecast-remaining-corrected')).to_have_text('—' if pr is None else '0' if pr == 0 else '47.616')
    bar = page.locator('#forecast-days .day-bar.corrected').first
    if pr is None:
        assert 'linear-gradient' in await bar.evaluate('node => getComputedStyle(node).backgroundImage')
    elif pr == 0:
        assert await bar.evaluate('node => node.getBoundingClientRect().height') == 0
    else:
        assert await bar.evaluate('node => node.getBoundingClientRect().height') == 70
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr').first.locator('td').nth(5)).to_have_text('—' if pr is None else '0' if pr == 0 else '4,464')



@pytest.mark.parametrize('width', [1440, 390])
async def test_downloads_emhass_forecast_csv(forecast_page, width, tmp_path):
    from fastapi import FastAPI
    from playwright.async_api import expect
    from test_integration import fake_server

    page, state, web = forecast_page
    view = state['view'] = forecast_payload('2026-11-18', 'Asia/Shanghai')
    view['correction']['pr'] = 50
    for row, watts in zip(view['intervals'][94:98], [0, 600.5, 1600, 2400.5]):
        row.update(forecast_power_w=watts, corrected_forecast_power_w=watts / 2,
                   forecast_energy_kwh=watts / 4000, corrected_forecast_energy_kwh=watts / 8000)

    app = FastAPI()
    mount = '/api/hassio_ingress/forecast-test' if width == 390 else ''
    app.mount(mount, web)
    await page.set_viewport_size({'width': width, 'height': 844})
    async with fake_server(app) as url:
        await page.goto(url + mount + '/')
        await expect(page.locator('main[data-configuration-ready=true][data-snapshot-ready=true]')).to_be_visible()
        await page.evaluate('now => Date.now = () => now', view['calculated_at'] * 1000)
        if width == 390:
            await page.locator('#language-select').select_option('fr')
            await page.locator('#theme-select').select_option('dark')
        await page.locator('#forecast-tab').click()
        chart_day = page.locator('#forecast-days button[data-day="2026-11-19"]')
        await chart_day.click()

        trigger = page.locator('#forecast-refresh + #forecast-export')
        await expect(trigger).to_be_enabled()
        requests = state['hourly']
        if width == 390:
            await expect(trigger).to_have_text('Exporter le CSV')
            for button in [page.locator('#forecast-refresh'), trigger]:
                box = await button.bounding_box()
                assert 0 <= box['x'] < box['x'] + box['width'] <= width
        else:
            refresh = await page.locator('#forecast-refresh').bounding_box()
            export = await trigger.bounding_box()
            assert refresh['x'] + refresh['width'] <= export['x']
            assert refresh['y'] == pytest.approx(export['y'], abs=1)
        await trigger.click()

        dialog = page.get_by_role('dialog')
        await expect(dialog).to_have_accessible_name('Exporter le CSV EMHASS' if width == 390 else 'Export EMHASS CSV')
        if width == 390:
            box = await dialog.bounding_box()
            assert 0 <= box['x'] < box['x'] + box['width'] <= width
            assert 0 <= box['y'] < box['y'] + box['height'] <= 844
            assert await dialog.evaluate('node => node.scrollWidth <= node.clientWidth')
        await expect(dialog.locator('#forecast-export-date')).to_have_value('2026-11-18')
        power = dialog.locator('#forecast-export-power')
        await expect(power.locator('option:checked')).to_have_text('Prévision originale' if width == 390 else 'Original forecast')
        step = dialog.locator('#forecast-export-step')
        await expect(step).to_have_value('30')
        start = dialog.locator('#forecast-export-start')
        await start.select_option(label='23:30')
        await step.select_option('60')
        await expect(start.locator('option:checked')).to_have_text('23:30')
        await step.select_option('30')
        steps = dialog.locator('#forecast-export-steps')
        await steps.fill('2')
        preview = dialog.get_by_role('status')
        await expect(preview).to_contain_text('23:30')
        await expect(preview).to_contain_text('00:30')
        download_button = dialog.get_by_role('button', name='Télécharger' if width == 390 else 'Download', exact=True)
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value
        assert download.suggested_filename == 'data_weather_forecast.csv'
        csv_path = tmp_path / download.suggested_filename
        await download.save_as(csv_path)
        assert csv_path.read_bytes() == b'2026-11-18 15:30:00+00:00,300.25\n2026-11-18 16:00:00+00:00,2000.25\n'

        if width == 1440:
            await power.select_option(label='Corrected forecast')
            async with page.expect_download() as download_info:
                await download_button.click()
            await (await download_info.value).save_as(csv_path)
            assert [float(row.split(b',')[1]) for row in csv_path.read_bytes().splitlines()] == [150.125, 1000.125]
        await page.keyboard.press('Escape')
        await expect(dialog).to_be_hidden()
        await expect(trigger).to_be_focused()
        await expect(chart_day).to_have_attribute('aria-pressed', 'true')
        assert state['hourly'] == requests


async def test_forecast_export_availability(forecast_page, tmp_path):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    view = forecast_payload()
    state['view'] = {**view, 'intervals': [], 'status': 'loading'}
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    trigger = page.locator('#forecast-export')
    await expect(trigger).to_be_disabled()

    view['correction']['pr'] = None
    view.update(status='partial', fetched_at=view['fetched_at'] + 1, calculated_at=view['calculated_at'] + 1)
    for row in view['intervals']:
        row.update(corrected_forecast_power_w=None, corrected_forecast_energy_kwh=None)
    view['intervals'][1].update(forecast_power_w=None, forecast_energy_kwh=None, quality='unavailable')
    state['view'] = view
    await expect(trigger).to_be_enabled(timeout=6000)
    await trigger.click()
    dialog = page.get_by_role('dialog')
    power = dialog.locator('#forecast-export-power')
    corrected = power.get_by_role('option', name='Corrected forecast')
    await expect(corrected).to_have_js_property('disabled', True)
    await expect(dialog.get_by_text('historical PR', exact=False)).to_be_visible()
    download_button = dialog.get_by_role('button', name='Download', exact=True)
    steps = dialog.locator('#forecast-export-steps')
    await steps.fill('1')
    await expect(download_button).to_be_disabled()
    await dialog.locator('#forecast-export-start').select_option(label='00:00')
    await dialog.locator('#forecast-export-step').select_option('15')
    await expect(download_button).to_be_enabled()
    await steps.fill('1.5')
    await expect(download_button).to_be_disabled()
    await steps.fill('0')
    await expect(download_button).to_be_disabled()
    await steps.fill('2')
    await expect(download_button).to_be_disabled()
    await expect(dialog.get_by_role('status')).to_contain_text('00:15')

    stale = copy.deepcopy(view)
    stale.update(status='stale', fetched_at=view['fetched_at'] + 1, calculated_at=view['calculated_at'] + 1)
    stale['correction']['pr'] = 0
    for row in stale['intervals']:
        if row['forecast_power_w'] is not None:
            row.update(corrected_forecast_power_w=0, corrected_forecast_energy_kwh=0)
    state['view'] = stale
    await expect(corrected).to_have_js_property('disabled', False, timeout=6000)
    await expect(dialog.get_by_text('Last successful fetch:', exact=False)).to_have_text(await page.locator('#forecast-fetched').inner_text())
    await power.select_option(label='Corrected forecast')
    await steps.fill('1')
    async with page.expect_download() as download_info:
        await download_button.click()
    csv_path = tmp_path / 'zero.csv'
    await (await download_info.value).save_as(csv_path)
    assert csv_path.read_bytes() == b'2026-11-01 00:00:00+00:00,0\n'

    view = {**view, 'fetched_at': stale['fetched_at'] + 1, 'calculated_at': stale['calculated_at'] + 1}
    state['view'] = view
    await expect(corrected).to_have_js_property('disabled', True, timeout=6000)
    await expect(dialog.get_by_text('historical PR', exact=False)).to_be_visible()
    await expect(download_button).to_be_disabled()


async def test_forecast_export_tracks_matching_detail(forecast_page):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await page.locator('#forecast-export').click()
    dialog = page.get_by_role('dialog')
    start = dialog.locator('#forecast-export-start')
    await start.select_option(label='00:00')
    await dialog.locator('#forecast-export-steps').fill('2')
    download_button = dialog.get_by_role('button', name='Download', exact=True)
    await expect(download_button).to_be_enabled()

    view = state['view']
    state['light'] = {**view, 'fetched_at': view['fetched_at'] + 1, 'calculated_at': view['calculated_at'] + 1}
    await expect(download_button).to_be_disabled(timeout=6000)
    await expect(dialog).to_be_visible()
    await expect(dialog.locator('#forecast-export-steps')).to_have_value('2')


async def test_forecast_export_repeated_start_time(forecast_page, tmp_path):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    state['view'] = forecast_payload('2026-11-01', 'America/New_York')
    await page.locator('#forecast-tab').click()
    await page.locator('#forecast-export').click()
    dialog = page.get_by_role('dialog')
    start = dialog.locator('#forecast-export-start')
    repeated = start.get_by_role('option', name='01:00', exact=False)
    await expect(repeated).to_have_text(['01:00 GMT-4', '01:00 GMT-5'])
    values = await repeated.evaluate_all('options => options.map(option => Number(option.value))')
    assert values[1] - values[0] == 3600
    await start.select_option(label='01:00 GMT-5')
    await dialog.locator('#forecast-export-steps').fill('1')
    async with page.expect_download() as download_info:
        await dialog.get_by_role('button', name='Download', exact=True).click()
    csv_path = tmp_path / 'repeated-time.csv'
    await (await download_info.value).save_as(csv_path)
    assert csv_path.read_bytes() == b'2026-11-01 06:00:00+00:00,3720\n'


@pytest.mark.parametrize('refresh', ['missing_power', 'rolled_day'])
async def test_forecast_export_reports_unavailable_selected_start(forecast_page, refresh):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await page.locator('#forecast-export').click()
    dialog = page.get_by_role('dialog')
    date = dialog.locator('#forecast-export-date')
    start = dialog.locator('#forecast-export-start')
    selected = await start.select_option(label='00:30')
    await dialog.locator('#forecast-export-steps').fill('1')
    download = dialog.get_by_role('button', name='Download', exact=True)
    await expect(download).to_be_enabled()

    view = copy.deepcopy(state['view'])
    if refresh == 'rolled_day':
        view = forecast_payload('2026-11-02')
    else:
        view['status'] = 'partial'
        view['intervals'][2].update(forecast_power_w=None, corrected_forecast_power_w=None,
                                    forecast_energy_kwh=None, corrected_forecast_energy_kwh=None,
                                    quality='unavailable')
        view['fetched_at'] += 1
        view['calculated_at'] += 1
    state['view'] = view

    await expect(download).to_be_disabled(timeout=6000)
    await expect(dialog.get_by_role('status')).to_contain_text('step starting at', timeout=6000)
    await expect(dialog.get_by_role('status')).to_contain_text('00:30')
    await expect(date).to_have_value('2026-11-01')
    await expect(start).to_have_value(selected[0])
    if refresh == 'rolled_day':
        await date.select_option('2026-11-02')
    await start.select_option(label='01:00')
    await expect(download).to_be_enabled()


async def test_forecast_export_labels_repeated_start_with_missing_power(forecast_page, tmp_path):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    view = state['view'] = forecast_payload('2026-11-01', 'America/New_York')
    view['intervals'][5].update(forecast_power_w=None, corrected_forecast_power_w=None,
                                forecast_energy_kwh=None, corrected_forecast_energy_kwh=None,
                                quality='unavailable')
    await page.locator('#forecast-tab').click()
    await page.locator('#forecast-export').click()
    dialog = page.get_by_role('dialog')
    start = dialog.locator('#forecast-export-start')
    await expect(start.get_by_role('option', name='01:15', exact=False)).to_have_text(['01:15 GMT-5'])
    await start.select_option(label='01:15 GMT-5')
    await dialog.locator('#forecast-export-steps').fill('1')
    async with page.expect_download() as download_info:
        await dialog.get_by_role('button', name='Download', exact=True).click()
    csv_path = tmp_path / 'remaining-repeated-time.csv'
    await (await download_info.value).save_as(csv_path)
    assert csv_path.read_bytes() == b'2026-11-01 06:15:00+00:00,3720\n'
