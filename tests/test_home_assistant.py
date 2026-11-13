import httpx
import pytest

from pvyieldlens.home_assistant import HAState, HomeAssistantClient, parse_state, entity_payloads


def state(value='1.5', unit='kW', changed='2026-10-28T00:00:00+00:00', reported='2026-10-28T00:10:00+00:00'):
    return HAState.model_validate({'entity_id': 'sensor.power', 'state': value,
        'attributes': {'unit_of_measurement': unit, 'friendly_name': 'Power'},
        'last_updated': changed, 'last_changed': changed, 'last_reported': reported})


def test_units_and_report_are_distinct_observations():
    points = parse_state(state(), 'power')
    assert [point.value for point in points] == [1500, 1500]
    assert points[1].at - points[0].at == 600
    assert len(parse_state(state(), 'power', historical=True)) == 1


@pytest.mark.parametrize('value,unit', [('unknown','W'), ('NaN','W'), ('-1','W'), ('3','kWh'), ('1e999','W')])
def test_invalid_values_end_validity(value, unit):
    assert all(point.value is None for point in parse_state(state(value, unit), 'power'))


def test_fahrenheit_temperature_conversion():
    assert parse_state(state('77', '°F'), 'temperature')[0].value == 25


async def test_selected_states_read_live_reports_and_keep_missing_sources_unavailable():
    def respond(request):
        if request.url.path == '/api/template':
            return httpx.Response(200, json=[state().model_dump(mode='json'), None])
        return httpx.Response(200, json=state(reported='2026-10-28T00:00:00+00:00').model_dump(mode='json'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = HomeAssistantClient('http://ha.test', 'secret', http=http)
        selected = await client.states(('sensor.power', 'sensor.missing'))
        assert parse_state(selected[0], 'power')[-1].at == 1793146200
        assert selected[1].entity_id == 'sensor.missing'
        assert selected[1].state == 'unavailable'


async def test_supervisor_urls_auth_history_and_publish():
    requests = []
    def respond(request):
        requests.append(request)
        if '/history/' in request.url.path:
            return httpx.Response(200, json=[[state().model_dump(mode='json')]])
        return httpx.Response(200, json={})
    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    client = HomeAssistantClient('http://supervisor/core', 'secret', http=http)
    assert client.websocket_url == 'ws://supervisor/core/websocket'
    await client.history(['sensor.power'], 1793145600, 1793146200)
    await client.publish({'sensor.pvyieldlens_pr': {'state': '90', 'attributes': {'unit_of_measurement': '%'}}})
    assert requests[0].headers['Authorization'] == 'Bearer secret'
    assert requests[0].url.params['filter_entity_id'] == 'sensor.power'
    assert requests[0].url.params['significant_changes_only'] == '0'
    assert requests[0].url.params['skip_initial_state'] == '1'
    assert requests[1].url.path == '/core/api/states/sensor.pvyieldlens_pr'
    await http.aclose()


def test_nine_outputs_keep_night_pr_unavailable():
    snapshot = {'statistics': {'estimated_power': 0, 'actual_power': 0, 'pr': None, 'quality': 'complete'},
                'realtime': None, 'energy': {'daily_kwh': 0.1, 'total_kwh': 1.2}, 'calculated_at': 123, 'revision': 1}
    payloads = entity_payloads(snapshot)
    original_ids = ('estimated_power', 'actual_power', 'pr', 'daily_estimated_energy', 'total_estimated_energy',
                    'realtime_estimated_power', 'realtime_actual_power', 'realtime_pr', 'realtime_optimizable_power')
    original_payloads = {name: payloads['sensor.pvyieldlens_' + name] for name in original_ids}
    assert len(original_payloads) == 9
    assert len(payloads) == 13
    assert original_payloads['pr']['state'] == 'unavailable'
    assert original_payloads['total_estimated_energy']['state'] == '1.2'
    assert original_payloads['total_estimated_energy']['attributes']['state_class'] == 'total_increasing'
    assert original_payloads['estimated_power']['attributes']['state_class'] == 'measurement'
    forecast_payloads = [payload for entity, payload in payloads.items() if entity.startswith('sensor.pvyieldlens_forecast_')]
    assert len(forecast_payloads) == 4
    assert all(payload['state'] == 'unavailable' for payload in forecast_payloads)
    assert all('state_class' not in payload['attributes'] for payload in forecast_payloads)


async def test_recorder_attribute_change_keeps_update_time_without_reported_timestamp():
    recorded = state(changed='2026-10-27T00:00:00+00:00').model_dump(mode='json')
    recorded['last_updated'] = '2026-10-28T00:01:00+00:00'
    recorded.pop('last_reported')
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200,json=[[recorded]])))
    client = HomeAssistantClient('http://ha.test', 'secret', http=http)
    history = await client.history(['sensor.power'], 1793145600, 1793146200)
    assert history[0].last_reported is None
    assert len(parse_state(history[0], 'power', historical=True)) == 1
    assert parse_state(history[0], 'power', historical=True)[0].at == 1793145660
    await http.aclose()


def test_statistics_keep_their_own_configuration_revision():
    payloads = entity_payloads({'statistics':{'estimated_power':3720,'revision':1},
        'realtime':None,'energy':{},'calculated_at':200,'revision':2})
    assert payloads['sensor.pvyieldlens_estimated_power']['attributes']['configuration_revision'] == 1


@pytest.mark.parametrize('latitude,longitude', [(31.23, 121.47), (0.0, 0.0), (-90.0, 180.0)])
async def test_configuration_parses_optional_site_with_active_origin(latitude, longitude):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        'latitude': latitude, 'longitude': longitude, 'location_name': 'Home', 'time_zone': 'Asia/Shanghai',
        'unit_system': {'length': 'km'}, 'version': '2026.11.0',
    }))) as http:
        client = HomeAssistantClient('http://ha.test/', 'secret', http=http)
        config = await client.configuration()
        assert config.time_zone == 'Asia/Shanghai'
        assert config.location.origin == 'http://ha.test'
        assert config.location.latitude == latitude
        assert config.location.longitude == longitude
        assert config.location.location_name == 'Home'
        assert config.location.timezone == 'Asia/Shanghai'


@pytest.mark.parametrize('site', [
    {}, {'latitude': 91.0, 'longitude': 0.0}, {'latitude': 0.0, 'longitude': -181.0},
    {'latitude': '31.23', 'longitude': 121.47}, {'latitude': None, 'longitude': 0.0},
    {'latitude': 0.0, 'longitude': 0.0, 'location_name': 123},
])
async def test_invalid_optional_location_does_not_break_monitoring_timezone(site):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'time_zone': 'UTC', **site},
    ))) as http:
        config = await HomeAssistantClient('http://ha.test', 'secret', http=http).configuration()
        assert config.time_zone == 'UTC'
        assert config.location is None


@pytest.mark.parametrize('fetched_at,status', [(43000.0, 'partial'), (1.0, 'stale')])
def test_forecast_entities_have_no_state_class(fetched_at, status):
    from forecast_fixtures import constant_intervals, forecast_input
    from pvyieldlens.forecast import ForecastBatch, forecast_view
    from pvyieldlens.settings import ForecastSettings

    inputs = forecast_input()
    view = forecast_view(ForecastBatch(inputs=inputs, fetched_at=fetched_at,
        intervals=constant_intervals(0, 2 * 86400)), inputs,
        ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0), 43200)
    payloads = entity_payloads({'statistics': None, 'realtime': None, 'energy': {},
        'calculated_at': 123, 'revision': 1, 'forecast': view.model_dump(mode='json', exclude={'days', 'intervals'})})
    targets = (
        ('sensor.pvyieldlens_forecast_energy_today', '89.28', 0, 86400, 100, 'complete'),
        ('sensor.pvyieldlens_forecast_energy_remaining_today', '44.64', 43200, 86400, 100, 'complete'),
        ('sensor.pvyieldlens_forecast_energy_tomorrow', '89.28', 86400, 172800, 100, 'complete'),
        ('sensor.pvyieldlens_forecast_energy_7d', 'unavailable', 0, 604800, 200 / 7, 'partial'),
    )
    assert len(payloads) == 13
    for entity, state_value, start, end, coverage, quality in targets:
        payload = payloads[entity]
        assert payload['state'] == state_value
        attributes = payload['attributes']
        assert attributes['unit_of_measurement'] == 'kWh'
        assert attributes['device_class'] == 'energy'
        assert 'state_class' not in attributes
        assert attributes['start'] == start
        assert attributes['end'] == end
        assert attributes['timezone'] == 'UTC'
        assert attributes['fetched_at'] == fetched_at
        assert attributes['calculated_at'] == 43200
        assert attributes['coverage_percent'] == pytest.approx(coverage)
        assert attributes['quality'] == quality
        assert attributes['status'] == status
