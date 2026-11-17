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
        return {'start': start, 'end': end, 'forecast_energy_kwh': 89.28, 'data_completeness_percent': 100, 'quality': 'complete'}
    rows = []
    start = boundaries[0] // 3600 * 3600
    while start < boundaries[-1]:
        left, right = max(start, boundaries[0]), min(start + 3600, boundaries[-1])
        rows.append({'start': left, 'end': right, 'irradiance_w_m2': 800, 'air_temperature_c': 20,
                     'cell_temperature_c': 45, 'forecast_power_w': 3720, 'forecast_energy_kwh': 3720 * (right-left) / 3600000,
                     'quality': 'complete'})
        start += 3600
    return {'status': 'ready', 'refreshing': False, 'fetched_at': boundaries[0] + 3600,
            'calculated_at': boundaries[0] + 48000, 'last_error': None, 'home_timezone': home_timezone,
            'today': total(boundaries[0], boundaries[1]),
            'remaining_today': {**total(boundaries[0]+48000, boundaries[1]), 'forecast_energy_kwh': 39.68},
            'tomorrow': total(boundaries[1], boundaries[2]),
            'seven_days': {**total(boundaries[0], boundaries[-1]), 'forecast_energy_kwh': 624.96},
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


async def test_forecast_days_select_hourly_details_and_preserve_selection(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button')).to_have_count(7)
    await expect(page.locator('#forecast-remaining')).to_have_text('39.68')
    await expect(page.locator('#forecast-tomorrow')).to_have_text('89.28')
    await expect(page.locator('#forecast-seven-days')).to_contain_text('624.96')
    await page.locator('#forecast-days button').nth(2).focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('#forecast-day-heading')).to_contain_text('Nov 3')
    await expect(page.locator('#forecast-day-total')).to_have_text('89.28 kWh')
    await page.locator('#forecast-details summary').click()
    await expect(page.locator('#forecast-rows tr')).to_have_count(24)
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('3,720')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('3.72')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('800')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('20')
    await expect(page.locator('#forecast-rows tr').first).to_contain_text('45')
    await expect(page.locator('#forecast-details th')).to_contain_text([
        'Interval', 'Irradiance', 'Air temperature', 'Estimated cell temperature', 'Forecast power', 'Interval energy'])
    await expect(page.locator('#forecast-chart svg')).to_have_attribute('aria-label', 'Forecast power')
    await page.locator('#forecast-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#forecast-chart .chart-tooltip')).to_contain_text('3.72 kWh')
    await expect(page.locator('#forecast-chart .chart-tooltip')).to_contain_text('3,720 W')
    await expect(page.locator('#forecast-fetched')).to_contain_text('Nov 1')
    await page.locator('#settings-button').click()
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-days button').nth(2)).to_have_attribute('aria-pressed', 'true')
    await page.locator('#forecast-refresh').click()
    await expect(page.locator('#forecast-refresh')).to_be_disabled()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-page')).to_be_visible()
    assert state['refresh'] == 1


@pytest.mark.parametrize('status', ['disabled', 'location_unavailable', 'unavailable', 'loading', 'partial', 'stale'])
async def test_forecast_states_are_truthful(forecast_page, status):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    view = state['view']
    view['status'] = status
    if status in ('disabled', 'location_unavailable', 'unavailable', 'loading'):
        view.update(fetched_at=None, days=[], intervals=[], today=None, remaining_today=None, tomorrow=None, seven_days=None)
    if status in ('partial', 'stale'):
        view['days'][1].update(forecast_energy_kwh=None, quality='partial', data_completeness_percent=50)
        view['seven_days'].update(forecast_energy_kwh=None, quality='partial', data_completeness_percent=92.85)
        view['tomorrow'] = view['days'][1]
        view['intervals'][36].update(forecast_power_w=None, forecast_energy_kwh=None, quality='unavailable')
    if status in ('unavailable', 'stale'):
        view['last_error'] = 'forecast_request_failed'
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-status')).to_have_attribute('data-status', status)
    if status in ('partial', 'stale'):
        await expect(page.locator('#forecast-seven-days')).to_have_text('— kWh')
        await expect(page.locator('#forecast-days button').first).to_contain_text('89.28')
        await page.locator('#forecast-days button').nth(1).click()
        await expect(page.locator('#forecast-day-total')).to_have_text('— kWh')
        await expect(page.locator('#forecast-day-data-completeness')).to_contain_text('50%')
        assert await page.locator('#forecast-chart path.series').evaluate("node => (node.getAttribute('d').match(/M/g) || []).length") == 2
        geometry = await page.locator('#forecast-chart').evaluate('''host => {
            const path = host.querySelector('path.series'), width = host.clientWidth - 60;
            return {left: path.getPointAtLength(0).x,
                right: path.getPointAtLength(path.getTotalLength()).x,
                edge: host.clientWidth - 12, gapStart: 48 + width / 2, gapEnd: 48 + width * 13 / 24,
                samples: Array.from({length: 2001}, (_, index) => path.getPointAtLength(path.getTotalLength() * index / 2000).x)};
        }''')
        assert geometry['left'] == pytest.approx(48, abs=0.05)
        assert geometry['right'] == pytest.approx(geometry['edge'], abs=0.05)
        assert all(x <= geometry['gapStart'] + 0.05 or x >= geometry['gapEnd'] - 0.05 for x in geometry['samples'])
        await expect(page.locator('#forecast-fetched')).to_contain_text('Nov 1')
        if status == 'stale':
            await expect(page.locator('#forecast-status')).to_contain_text('older')
            await expect(page.locator('#forecast-error')).not_to_be_empty()
    else:
        await expect(page.locator('#forecast-remaining')).to_have_text('—')
        await expect(page.locator('#forecast-fetched')).to_contain_text('No successful fetch')
    await page.locator('#open-forecast-settings').click()
    await expect(page.locator('[data-settings-section=forecast]')).to_be_visible()


async def test_scalar_poll_does_not_redraw_or_refetch_hourly_forecast(forecast_page):
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
    await expect(page.locator('#forecast-days button').first).to_have_attribute('data-day', '2026-11-02')
    assert state['view']['fetched_at'] == before_view['fetched_at']
    assert state['view']['remaining_today']['forecast_energy_kwh'] >= 0
    await expect(page.locator('#forecast-days button').first).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('#forecast-days [aria-current=date]')).to_have_attribute('data-day', '2026-11-02')


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
        await expect(page.locator('#forecast-rows tr')).to_have_count(25)
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
        await expect(page.locator('#forecast-chart svg')).to_have_attribute('aria-label', 'Puissance prévue')
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
    await expect(page.locator('#forecast-rows tr')).to_have_count(25)
    first, last = page.locator('#forecast-rows tr').first, page.locator('#forecast-rows tr').last
    await expect(first).to_contain_text('00:00')
    await expect(first).to_contain_text('00:45')
    await expect(first).to_contain_text('2.79')
    await expect(last).to_contain_text('23:45')
    await expect(last).to_contain_text('00:00')
    await expect(last).to_contain_text('0.93')
    await expect(page.locator('#forecast-day-total')).to_have_text('89.28 kWh')


async def test_shared_plot_keeps_gaps_and_readable_responsive_ticks(forecast_page):
    from playwright.async_api import expect
    page, state, _ = forecast_page
    state['view']['intervals'][12].update(forecast_power_w=None, forecast_energy_kwh=None, quality='unavailable')
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


async def test_forecast_and_monitoring_layout_evidence(forecast_page, browser_workspace, monkeypatch):
    from types import SimpleNamespace
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module
    from playwright.async_api import expect
    from test_engine import samples
    from pvyieldlens.engine import calculate
    from pvyieldlens.forecast import ForecastBatch, WeatherSample, calculate_forecast, forecast_view
    from pvyieldlens.settings import ForecastSettings
    from forecast_fixtures import forecast_input
    page, state, _ = forecast_page
    _, service, _ = browser_workspace
    start = service.store.cursor
    now = start + 1800
    clock = SimpleNamespace(time=lambda: now)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    await page.evaluate('now => Date.now = () => now', now*1000)
    inputs = forecast_input()
    midnight = datetime.fromtimestamp(now, ZoneInfo('UTC')).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    weather = tuple(WeatherSample(at=midnight+i*3600, irradiance_w_m2=[0,0,0,0,0,0,20,100,300,500,650,800,850,700,500,300,100,20,0,0,0,0,0,0][i % 24], air_temperature_c=20, weather_code=0)
                    for i in range(7*24+1))
    state['view'] = forecast_view(ForecastBatch(inputs=inputs, fetched_at=now-1800,
        intervals=calculate_forecast(inputs, weather), weather_samples=weather), inputs,
        ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), now).model_dump(mode='json')
    for offset in range(0,1800,60):
        values = samples(power=2500 + offset/3, at=start+offset)
        service.store.settle(calculate(service.monitoring_settings, values, start+offset, start+offset+60), 1, 'UTC')
    service.store.add_observations(samples(at=now-60))
    await service.tick(now)
    await expect(page.locator('#live-actual')).to_have_text('3,348')
    path = Path('artifacts/task-7-layout')
    path.mkdir(parents=True, exist_ok=True)
    for size, width in [('desktop',1440),('mobile',390)]:
        await page.set_viewport_size({'width':width,'height':900 if width>600 else 844})
        for name, control in [('live','live-tab'),('history','history-tab'),('forecast','forecast-tab'),('settings','settings-button')]:
            await page.locator(f'#{control}').click()
            if name == 'settings':
                await page.emulate_media(reduced_motion='reduce')
                await page.locator('[data-settings-category=forecast]').click()
            if name == 'forecast':
                await expect(page.locator('#forecast-days button')).to_have_count(7)
                await expect(page.locator('#forecast-chart path')).to_be_visible()
            if name == 'history':
                await expect(page.locator('#history-chart path')).to_have_count(2)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(path/f'{name}-{size}.png'))
            if name == 'forecast':
                await page.locator('.forecast-hourly').scroll_into_view_if_needed()
                chart = await page.locator('#forecast-chart').bounding_box()
                assert chart['width'] > 0 and chart['x'] >= 0 and chart['x'] + chart['width'] <= width
                await page.screenshot(path=str(path/f'forecast-hourly-{size}.png'))
                await page.locator('#forecast-details summary').click()
                await page.locator('#forecast-details').evaluate('''details => {
                    const scroll = document.querySelector('#content-scroll');
                    scroll.scrollTo(0, scroll.scrollTop + details.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 16);
                }''')
                assert (await page.locator('#forecast-details').bounding_box())['y'] >= (await page.locator('.app-header').bounding_box())['height']
                await page.screenshot(path=str(path/f'forecast-details-{size}.png'))
                await page.locator('#forecast-details summary').click()
        await page.locator('#forecast-tab').click()


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
    await expect(page.locator('#forecast-status')).to_have_attribute('data-status', 'ready')
