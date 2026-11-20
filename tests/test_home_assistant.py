from datetime import datetime

import httpx
import pytest

from pvyieldlens.home_assistant import HAState, HomeAssistantClient, parse_state, entity_payloads, source_value


def state(value='1.5', unit='kW', changed='2026-10-28T00:00:00+00:00', reported='2026-10-28T00:10:00+00:00'):
    return HAState.model_validate({'entity_id': 'sensor.power', 'state': value,
        'attributes': {'unit_of_measurement': unit, 'friendly_name': 'Power'},
        'last_updated': changed, 'last_changed': changed, 'last_reported': reported})


def test_units_and_report_are_distinct_observations():
    points = parse_state(state(), 'power')
    assert [point.value for point in points] == [1500, 1500]
    assert points[1].at - points[0].at == 600
    assert len(parse_state(state(), 'power', historical=True)) == 1


@pytest.mark.parametrize('role,value,unit,expected', [
    ('power', '0', 'W', 0), ('power', 'unknown', 'W', None), ('power', 'NaN', 'W', None),
    ('power', '-1', 'W', None), ('power', '3', 'kWh', None), ('power', ' 1', 'W', None),
    ('power', '1e999', 'W', None), ('power', '1e308', 'kW', None),
    ('temperature', '-10', '°C', -10), ('temperature', '77', '°F', 25),
    ('temperature', '300', 'K', pytest.approx(26.85)), ('temperature', '300', 'C', None),
    ('irradiance', '800', 'W/m²', 800), ('irradiance', '.8', 'kW / m^2', 800),
    ('irradiance', '-1', 'W/m2', None), ('irradiance', '1', None, None),
    ('irradiance', 'unknown', 'W/m2', None),
])
def test_parse_state_normalizes_supported_units_and_ends_invalid_readings(role, value, unit, expected):
    assert [point.value for point in parse_state(state(value, unit), role)] == [expected, expected]


@pytest.mark.parametrize('value,unit,role,expected', [
    ('0', '°', 'tilt', 0), ('90', '°', 'tilt', 90), ('359.9', '°', 'azimuth', 359.9),
    ('unknown', '°', 'tilt', None), ('unavailable', '°', 'azimuth', None),
    ('NaN', '°', 'tilt', None), ('1e999', '°', 'azimuth', None),
    ('1', 'rad', 'tilt', None), ('1', None, 'azimuth', None),
    ('90.1', '°', 'tilt', None), ('360', '°', 'azimuth', None),
    ('-0.1', '°', 'tilt', None), ('-0.1', '°', 'azimuth', None),
])
def test_angle_source_value_uses_degree_units_and_axis_bounds(value, unit, role, expected):
    assert source_value(value, unit, role) == expected


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


async def test_state_discovery_accepts_non_string_attributes_alongside_valid_sensor():
    unusual = state().model_dump(mode='json')
    unusual['attributes'] = {'friendly_name': {'name': 'Power'}, 'unit_of_measurement': ['kW']}
    temperature = state('77', '°F').model_dump(mode='json')
    temperature.update(entity_id='sensor.temperature', attributes={'friendly_name': 'Temperature', 'unit_of_measurement': '°F'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=[unusual, temperature],
    ))) as http:
        power, temp = await HomeAssistantClient('http://ha.test', 'secret', http=http).states()

    assert power.entity_id == 'sensor.power'
    assert power.state == '1.5'
    assert power.last_changed.timestamp() == power.last_updated.timestamp() == 1793145600
    assert power.last_reported.timestamp() == 1793146200
    assert power.attributes.friendly_name is None
    assert power.attributes.unit_of_measurement is None
    assert parse_state(power, 'power')[0].value is None
    assert temp.attributes.friendly_name == 'Temperature'
    assert temp.attributes.unit_of_measurement == '°F'
    assert [(point.at, point.value) for point in parse_state(temp, 'temperature')] == [(1793145600, 25), (1793146200, 25)]


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
    await client.publish({'sensor.pvyieldlens_settled_pr': {'state': '90', 'attributes': {'unit_of_measurement': '%'}}})
    assert requests[0].headers['Authorization'] == 'Bearer secret'
    assert requests[0].url.params['filter_entity_id'] == 'sensor.power'
    assert requests[0].url.params['significant_changes_only'] == '0'
    assert requests[0].url.params['skip_initial_state'] == '1'
    assert requests[1].url.path == '/core/api/states/sensor.pvyieldlens_settled_pr'
    await http.aclose()


async def test_recorder_history_keeps_a_real_state_at_the_lower_bound():
    rows = [(recorded_at, state(value, changed=stamp, reported=None).model_dump(mode='json'))
            for recorded_at, value, stamp in (
        (1793145599.9999993, '1', '2026-10-27T23:59:59.999999+00:00'),
        (1793145600, '2', '2026-10-28T00:00:00+00:00'),
        (1793146200, '3', '2026-10-28T00:10:00+00:00'),
    )]

    def respond(request):
        start = datetime.fromisoformat(request.url.path.rsplit('/', 1)[-1]).timestamp()
        end = datetime.fromisoformat(request.url.params['end_time']).timestamp()
        return httpx.Response(200, json=[[row for recorded_at, row in rows if start < recorded_at < end]])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        history = await HomeAssistantClient('http://ha.test', 'secret', http=http).history(['sensor.power'], 1793145600, 1793146200)
    assert [(row.last_updated.timestamp(), row.state) for row in history] == [(1793145600, '2')]


def test_thirteen_outputs_use_scoped_names_and_keep_night_pr_unavailable():
    snapshot = {'latest_settled_window': {'estimated_power_w': 0, 'actual_power_w': 0, 'pr': None, 'quality': 'complete', 'data_completeness_percent': 100},
                'live_window': None, 'energy_totals': {'estimated_energy_today_kwh': 0.1, 'estimated_energy_lifetime_kwh': 1.2, 'home_timezone': 'UTC', 'today_valid_seconds': 60,
                                                       'lifetime_valid_seconds': 600, 'today_allocation_complete': True},
                'calculated_at': 123, 'revision': 1}
    payloads = entity_payloads(snapshot)
    definitions = (
        ('settled_estimated_power', 'W', 'power', 'measurement'),
        ('settled_actual_power', 'W', 'power', 'measurement'),
        ('settled_pr', '%', None, 'measurement'),
        ('estimated_energy_today', 'kWh', 'energy', 'total_increasing'),
        ('estimated_energy_lifetime', 'kWh', 'energy', 'total_increasing'),
        ('live_estimated_power', 'W', 'power', 'measurement'),
        ('live_actual_power', 'W', 'power', 'measurement'),
        ('live_pr', '%', None, 'measurement'),
        ('live_optimizable_power', 'W', 'power', 'measurement'),
        ('forecast_energy_today', 'kWh', 'energy', None),
        ('forecast_energy_remaining_today', 'kWh', 'energy', None),
        ('forecast_energy_tomorrow', 'kWh', 'energy', None),
        ('forecast_energy_7d', 'kWh', 'energy', None),
    )
    assert set(payloads) == {'sensor.pvyieldlens_' + suffix for suffix, *_ in definitions}
    for suffix, unit, device_class, state_class in definitions:
        attributes = payloads['sensor.pvyieldlens_' + suffix]['attributes']
        assert attributes['friendly_name'] == suffix
        assert attributes['unit_of_measurement'] == unit
        assert attributes.get('device_class') == device_class
        assert attributes.get('state_class') == state_class
    assert payloads['sensor.pvyieldlens_settled_pr']['state'] == 'unavailable'
    assert payloads['sensor.pvyieldlens_settled_pr']['attributes']['data_completeness_percent'] == 100
    totals = payloads['sensor.pvyieldlens_estimated_energy_today']['attributes']
    assert {key: totals[key] for key in ('home_timezone', 'today_valid_seconds', 'lifetime_valid_seconds',
                                       'today_allocation_complete')} == {
        'home_timezone': 'UTC', 'today_valid_seconds': 60, 'lifetime_valid_seconds': 600, 'today_allocation_complete': True}
    assert payloads['sensor.pvyieldlens_estimated_energy_lifetime']['state'] == '1.2'
    for entity, payload in payloads.items():
        if entity.startswith('sensor.pvyieldlens_forecast_'):
            assert payload['state'] == 'unavailable'
            assert payload['attributes']['status'] == 'configuration_required'


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


def test_settled_windows_keep_their_own_configuration_revision():
    payloads = entity_payloads({'latest_settled_window':{'estimated_power_w':3720,'revision':1},
        'live_window':None,'energy_totals':{},'calculated_at':200,'revision':2})
    assert payloads['sensor.pvyieldlens_settled_estimated_power']['attributes']['configuration_revision'] == 1
    assert payloads['sensor.pvyieldlens_settled_estimated_power']['state'] == '3720'


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
        assert config.location.home_timezone == 'Asia/Shanghai'


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

    inputs = forecast_input()
    view = forecast_view(ForecastBatch(inputs=inputs, fetched_at=fetched_at,
        intervals=constant_intervals(0, 2 * 86400), weather_samples=()), inputs.location, 43200)
    payloads = entity_payloads({'latest_settled_window': None, 'live_window': None, 'energy_totals': {},
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
        assert attributes['home_timezone'] == 'UTC'
        assert attributes['fetched_at'] == fetched_at
        assert attributes['calculated_at'] == 43200
        assert attributes['data_completeness_percent'] == pytest.approx(coverage)
        assert attributes['quality'] == quality
        assert attributes['status'] == status
