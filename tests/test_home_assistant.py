import json

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


@pytest.mark.parametrize('value,unit', [('unknown','W'), ('NaN','W'), ('-1','W'), ('3','kWh'), ('1e999','W')])
def test_invalid_values_end_validity(value, unit):
    assert all(point.value is None for point in parse_state(state(value, unit), 'power'))


def test_fahrenheit_temperature_conversion():
    assert parse_state(state('77', '°F'), 'temperature')[0].value == 25


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
    assert all(payload['state'] == 'unavailable' for entity, payload in payloads.items()
               if entity.startswith('sensor.pvyieldlens_forecast_'))


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
    from pvyieldlens.settings import ForecastSettings

    inputs = forecast_input()
    view = forecast_view(ForecastBatch(inputs=inputs, fetched_at=fetched_at,
        intervals=constant_intervals(0, 2 * 86400), weather_samples=()), inputs.location,
        ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0), 43200)
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


async def test_source_diagnostics_batches_configured_sources_and_reads_unchanged_reports():
    requests = []
    reports = iter((1793146200.0, 1793146201.0))

    def respond(request):
        requests.append(request)
        reported_at = next(reports)
        return httpx.Response(200, json={'observed_at': reported_at + 0.25, 'sources': [
            {'state': '1.500', 'unit': 'kW', 'reported_at': reported_at},
            {'state': '77', 'unit': '°F', 'reported_at': 1793145600},
            {'state': '0.8', 'unit': 'kW / m²', 'reported_at': None},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = HomeAssistantClient('http://ha.test', 'secret', http=http)
        first = await client.source_diagnostics(('sensor.power', 'sensor.temp', 'sensor.sun'))
        second = await client.source_diagnostics(('sensor.power', 'sensor.temp', 'sensor.sun'))
    assert first == {'observed_at': 1793146200.25, 'sources': [
        {'entity_id': 'sensor.power', 'state': '1.500', 'unit': 'kW', 'reported_at': 1793146200, 'valid': True},
        {'entity_id': 'sensor.temp', 'state': '77', 'unit': '°F', 'reported_at': 1793145600, 'valid': True},
        {'entity_id': 'sensor.sun', 'state': '0.8', 'unit': 'kW / m²', 'reported_at': None, 'valid': True},
    ]}
    assert second['observed_at'] == 1793146201.25
    assert second['sources'][0] == {**first['sources'][0], 'reported_at': 1793146201}
    assert len(requests) == 2
    assert all(request.method == 'POST' and request.url.path == '/api/template' for request in requests)
    assert all(json.loads(request.content)['variables'] == {
        'entities': ['sensor.power', 'sensor.temp', 'sensor.sun'],
    } for request in requests)
    assert all(request.headers['Authorization'] == 'Bearer secret' for request in requests)


@pytest.mark.parametrize('role,value,unit,valid', [
    ('power', '0', 'W', True), ('power', '1.5', 'kW', True),
    ('power', '-1', 'W', False), ('power', '3', 'kWh', False),
    ('power', ' 1', 'W', False), ('power', 'NaN', 'W', False),
    ('power', '1e999', 'W', False), ('power', '1e308', 'kW', False),
    ('temperature', '-10', '°C', True), ('temperature', '77', '°F', True),
    ('temperature', '300', 'K', True), ('temperature', '300', 'C', False),
    ('irradiance', '800', 'W/m²', True), ('irradiance', '.8', 'kW / m^2', True),
    ('irradiance', '-1', 'W/m2', False), ('irradiance', '1', None, False),
    ('irradiance', 'unknown', 'W/m2', False),
])
async def test_source_diagnostics_validity_matches_native_source_units(role, value, unit, valid):
    roles = ('power', 'temperature', 'irradiance')
    rows = [{'state': 'unavailable', 'unit': None, 'reported_at': None} for _ in roles]
    rows[roles.index(role)] = {'state': value, 'unit': unit, 'reported_at': 100.0}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'observed_at': 110.0, 'sources': rows},
    ))) as http:
        diagnostics = await HomeAssistantClient('http://ha.test', 'secret', http=http).source_diagnostics(
            ('sensor.power', 'sensor.temp', 'sensor.sun'))
    assert diagnostics['sources'][roles.index(role)]['valid'] is valid
    assert (parse_state(state(value, unit), role)[0].value is not None) is valid


async def test_source_diagnostics_missing_entities_have_no_synthetic_report_time():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'observed_at': 123.5, 'sources': [None, None, None]},
    ))) as http:
        result = await HomeAssistantClient('http://ha.test', 'secret', http=http).source_diagnostics(
            ('sensor.power', 'sensor.temp', 'sensor.sun'))
    assert result == {'observed_at': 123.5, 'sources': [
        {'entity_id': 'sensor.power', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False},
        {'entity_id': 'sensor.temp', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False},
        {'entity_id': 'sensor.sun', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False},
    ]}


@pytest.mark.parametrize('field,value', [
    ('observed_at', None), ('observed_at', 'invalid'), ('observed_at', '123'), ('observed_at', True),
    ('observed_at', float('nan')), ('observed_at', float('inf')), ('observed_at', -float('inf')),
    ('reported_at', 'invalid'), ('reported_at', '123'), ('reported_at', False),
    ('reported_at', float('nan')), ('reported_at', float('inf')), ('reported_at', -float('inf')),
    ('state', 123), ('unit', 123),
])
async def test_source_diagnostics_rejects_invalid_boundary_values(field, value):
    row = {'state': '1', 'unit': 'W', 'reported_at': 100.0}
    payload = {'observed_at': 110.0, 'sources': [row, None, None]}
    if field == 'observed_at':
        payload[field] = value
    else:
        row[field] = value
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=json.dumps(payload), headers={'Content-Type': 'application/json'},
    ))) as http:
        with pytest.raises(ValueError):
            await HomeAssistantClient('http://ha.test', 'secret', http=http).source_diagnostics(
                ('sensor.power', 'sensor.temp', 'sensor.sun'))


@pytest.mark.parametrize('rows', [[], [None], [None, None, None, None]])
async def test_source_diagnostics_rejects_incomplete_or_extra_source_rows(rows):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'observed_at': 110.0, 'sources': rows},
    ))) as http:
        with pytest.raises(ValueError):
            await HomeAssistantClient('http://ha.test', 'secret', http=http).source_diagnostics(
                ('sensor.power', 'sensor.temp', 'sensor.sun'))


async def test_source_diagnostics_ha_simulator_supports_missing_configured_sources():
    import fake_ha

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fake_ha.app)) as http:
        client = HomeAssistantClient('http://ha.test', 'simulation-token', http=http)
        result = await client.source_diagnostics(('sensor.power', 'sensor.temp', 'sensor.missing'))
        selected = await client.states(('sensor.power', 'sensor.temp'))
    assert result['observed_at'] > 0
    assert [source['entity_id'] for source in result['sources']] == ['sensor.power', 'sensor.temp', 'sensor.missing']
    assert result['sources'][0]['unit'] == 'W'
    assert result['sources'][0]['valid'] is True
    assert result['sources'][0]['reported_at'] == pytest.approx(result['observed_at'], rel=0, abs=1e-6)
    assert result['sources'][1]['state'] == '45'
    assert result['sources'][1]['unit'] == '°C'
    assert result['sources'][1]['valid'] is True
    assert result['sources'][2] == {
        'entity_id': 'sensor.missing', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False,
    }
    assert [source.entity_id for source in selected] == ['sensor.power', 'sensor.temp']
    assert selected[1].state == '45'
