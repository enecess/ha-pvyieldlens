import json

import httpx
import pytest
from pydantic import JsonValue

from pvyieldlens.engine import Observation
from pvyieldlens.open_meteo import OpenMeteoClient
from pvyieldlens.settings import AmbientSite
from forecast_fixtures import forecast_input, forecast_payload


@pytest.mark.parametrize('azimuth_deg,provider_azimuth', [(0, -180), (90, -90), (180, 0), (270, 90)])
@pytest.mark.parametrize('latitude,longitude,tilt_deg', [(0, 0, 0), (31.2, 121.5, 25), (-33.9, -70.7, 90)])
async def test_request_uses_only_forecast_inputs(azimuth_deg, provider_azimuth, latitude, longitude, tilt_deg):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=forecast_payload(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = OpenMeteoClient(http=http)
        fetched = await client.fetch(forecast_input(
            latitude=latitude, longitude=longitude, tilt_deg=tilt_deg, azimuth_deg=azimuth_deg,
            origin='http://ha.test/private', home_timezone='Asia/Shanghai',
        ))
    request, = requests
    assert request.method == 'GET'
    assert (request.url.scheme, request.url.host, request.url.path) == ('https', 'api.open-meteo.com', '/v1/forecast')
    assert set(request.url.params) == {
        'latitude', 'longitude', 'tilt', 'azimuth', 'hourly', 'minutely_15', 'temperature_unit',
        'timezone', 'timeformat', 'past_days', 'forecast_days',
    }
    assert float(request.url.params['latitude']) == latitude
    assert float(request.url.params['longitude']) == longitude
    assert float(request.url.params['tilt']) == tilt_deg
    assert float(request.url.params['azimuth']) == provider_azimuth
    assert request.url.params['minutely_15'] == 'global_tilted_irradiance,temperature_2m'
    assert request.url.params['hourly'] == 'global_tilted_irradiance,temperature_2m,weather_code'
    assert request.url.params['temperature_unit'] == 'celsius'
    assert request.url.params['timezone'] == 'UTC'
    assert request.url.params['timeformat'] == 'unixtime'
    assert (request.url.params['past_days'], request.url.params['forecast_days']) == ('1', '8')
    assert 'authorization' not in request.headers
    assert request.extensions['timeout'] == {'connect': 20, 'read': 20, 'write': 20, 'pool': 20}
    assert len(fetched.intervals) == 864
    assert len(fetched.weather_samples) == 217
    assert all(row.end - row.start == 900 for row in fetched.intervals)
    assert fetched.weather_samples[1].at - fetched.weather_samples[0].at == 3600


async def test_close_preserves_injected_http_client():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as http:
        client = OpenMeteoClient(http=http)
        await client.close()
        assert not http.is_closed


async def test_close_releases_owned_http_client():
    client = OpenMeteoClient()
    await client.close()
    assert client.http.is_closed


async def fetch_payload(payload: JsonValue):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(payload)),
    )) as http:
        client = OpenMeteoClient(http=http)
        return (await client.fetch(forecast_input())).intervals


async def test_quarter_hour_backward_mean_and_temperature_alignment():
    payload = forecast_payload(0)
    payload['minutely_15']['global_tilted_irradiance'][:3] = [None, 800, 400]
    payload['minutely_15']['temperature_2m'][:3] = [10, 30, 10]
    intervals = await fetch_payload(payload)
    assert len(intervals) == 864
    first, second = intervals[:2]
    assert (first.start, first.end, first.irradiance_w_m2, first.air_temperature_c) == (0, 900, 800, 20)
    assert first.cell_temperature_c == 45
    assert first.forecast_power_w == pytest.approx(3720)
    assert first.forecast_energy_kwh == pytest.approx(0.93)
    assert (second.start, second.end, second.irradiance_w_m2, second.air_temperature_c) == (900, 1800, 400, 20)
    assert second.cell_temperature_c == 32.5
    assert second.forecast_power_w == pytest.approx(1947.5)
    assert second.forecast_energy_kwh == pytest.approx(0.486875)
    assert (intervals[-1].start, intervals[-1].end) == (776700, 777600)


async def test_quarter_hour_null_is_not_night_zero():
    payload = forecast_payload(0, hours=1)
    payload['minutely_15']['global_tilted_irradiance'] = [800, None, 0, 800, 800]
    missing, night, daylight, _ = await fetch_payload(payload)
    assert (missing.start, missing.end, missing.irradiance_w_m2, missing.forecast_power_w, missing.forecast_energy_kwh) == (0, 900, None, None, None)
    assert missing.quality == 'unavailable'
    assert (night.start, night.end, night.irradiance_w_m2, night.forecast_power_w, night.forecast_energy_kwh) == (900, 1800, 0, 0, 0)
    assert night.quality == 'complete'
    assert daylight.forecast_power_w == pytest.approx(3720)
    assert daylight.quality == 'complete'


@pytest.mark.parametrize('value', [None, -1, float('nan'), float('inf'), float('-inf'), '800', True, {}, []])
async def test_invalid_irradiance_keeps_interval_position(value):
    payload = forecast_payload(0, hours=1)
    payload['minutely_15']['global_tilted_irradiance'][2] = value
    intervals = await fetch_payload(payload)
    assert len(intervals) == 4
    assert (intervals[1].start, intervals[1].end, intervals[1].irradiance_w_m2) == (900, 1800, None)
    assert intervals[1].forecast_power_w is intervals[1].forecast_energy_kwh is None
    assert intervals[1].quality == 'unavailable'
    assert intervals[0].forecast_power_w == intervals[2].forecast_power_w == pytest.approx(3720)


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), float('-inf'), '20', False, {}, []])
async def test_invalid_temperature_keeps_affected_intervals(value):
    payload = forecast_payload(0, hours=1)
    payload['minutely_15']['temperature_2m'][1] = value
    intervals = await fetch_payload(payload)
    assert len(intervals) == 4
    assert [(row.start, row.end) for row in intervals] == [(0, 900), (900, 1800), (1800, 2700), (2700, 3600)]
    assert [row.air_temperature_c for row in intervals] == [None, None, 20, 20]
    assert [row.quality for row in intervals] == ['unavailable', 'unavailable', 'complete', 'complete']
    assert intervals[0].forecast_power_w is intervals[1].forecast_power_w is None
    assert intervals[2].forecast_power_w == pytest.approx(3720)


async def test_negative_air_temperature_remains_valid():
    row = (await fetch_payload(forecast_payload(0, hours=1, air_temperature_c=-10)))[0]
    assert row.air_temperature_c == -10
    assert row.cell_temperature_c == 15
    assert row.forecast_power_w == pytest.approx(4140)
    assert row.quality == 'complete'


@pytest.mark.parametrize('grid', ['hourly', 'minutely_15'])
@pytest.mark.parametrize('units,field,value', [
    (False, 'time', [0, 0, 7200]),
    (False, 'time', [0, 7200, 3600]),
    (False, 'time', [0, 1800, 3600]),
    (False, 'time', [0, 3600, float('nan')]),
    (False, 'time', [0, 3600, float('inf')]),
    (False, 'time', [0, 3600, float('-inf')]),
    (False, 'time', [0, 3600, None]),
    (False, 'time', [0, 3600, '7200']),
    (False, 'time', [False, 3600, 7200]),
    (False, 'time', []),
    (False, 'time', {}),
    (False, 'global_tilted_irradiance', [800, 800]),
    (False, 'global_tilted_irradiance', None),
    (False, 'temperature_2m', [20, 20, 20, 20]),
    (False, 'temperature_2m', '20'),
    (True, 'time', 'iso8601'),
    (True, 'global_tilted_irradiance', 'W/m2'),
    (True, 'global_tilted_irradiance', None),
    (True, 'temperature_2m', '°F'),
])
async def test_malformed_minutely_or_hourly_batch_is_rejected(grid, units, field, value):
    payload = forecast_payload(0, hours=2)
    payload[f'{grid}_units' if units else grid][field] = value
    with pytest.raises(ValueError):
        await fetch_payload(payload)


@pytest.mark.parametrize('grid', ['hourly', 'minutely_15'])
@pytest.mark.parametrize('units,field', [
    (False, 'time'), (False, 'global_tilted_irradiance'), (False, 'temperature_2m'),
    (True, 'time'), (True, 'global_tilted_irradiance'), (True, 'temperature_2m'),
])
async def test_required_minutely_or_hourly_field_is_rejected_when_missing(grid, units, field):
    payload = forecast_payload(0)
    del payload[f'{grid}_units' if units else grid][field]
    with pytest.raises(ValueError):
        await fetch_payload(payload)


@pytest.mark.parametrize('grid', ['hourly', 'minutely_15'])
async def test_missing_minutely_or_hourly_group_is_rejected(grid):
    payload = forecast_payload(0)
    del payload[grid]
    with pytest.raises(ValueError):
        await fetch_payload(payload)


async def test_missing_minutely_interval_with_intact_hourly_weather_is_rejected():
    payload = forecast_payload(0, hours=2, weather_code=61)
    for field in ('time', 'global_tilted_irradiance', 'temperature_2m'):
        del payload['minutely_15'][field][3]
    with pytest.raises(ValueError, match='minutely_15'):
        await fetch_payload(payload)


@pytest.mark.parametrize('payload', [None, [], 'weather', {}, {'hourly': []}, forecast_payload(0, hours=0)])
async def test_incomplete_response_shape_is_rejected(payload):
    with pytest.raises(ValueError):
        await fetch_payload(payload)


@pytest.mark.parametrize('status', [429, 500])
async def test_http_failure_is_propagated(status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={'error': True, 'reason': 'weather unavailable'}),
    )) as http:
        client = OpenMeteoClient(http=http)
        with pytest.raises(httpx.HTTPStatusError) as failure:
            await client.fetch(forecast_input())
    assert failure.value.response.status_code == status


async def test_transport_failure_is_propagated():
    def respond(request):
        raise httpx.ReadTimeout('forecast timed out', request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = OpenMeteoClient(http=http)
        with pytest.raises(httpx.ReadTimeout):
            await client.fetch(forecast_input())


async def test_invalid_json_is_rejected():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b'{'),
    )) as http:
        client = OpenMeteoClient(http=http)
        with pytest.raises(json.JSONDecodeError):
            await client.fetch(forecast_input())


@pytest.mark.parametrize('value,expected', [
    (0, 0), (61, 61), (95, 95), (96, 96), (97, 97), (99, 99),
    (None, None), (100, None), ('61', None), (True, None), (False, None),
    (61.0, None), (float('nan'), None), (float('inf'), None), (float('-inf'), None),
])
async def test_weather_codes_do_not_invalidate_power(value, expected):
    payload = forecast_payload(0, hours=2, weather_code=0)
    payload['hourly']['weather_code'][1] = value
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(payload)),
    )) as http:
        fetched = await OpenMeteoClient(http).fetch(forecast_input())
    assert fetched.intervals[0].forecast_power_w == pytest.approx(3720)
    assert fetched.intervals[1].forecast_power_w == pytest.approx(3720)
    assert [sample.weather_code for sample in fetched.weather_samples] == [0, expected, 0]


@pytest.mark.parametrize('section,value', [
    ('hourly', None), ('hourly', '61'), ('hourly', {}), ('hourly', [61]),
    ('hourly', [61, 61, 61, 61]), ('hourly_units', None), ('hourly_units', 'code'),
])
async def test_malformed_optional_codes_leave_core_weather_available(section, value):
    payload = forecast_payload(0, hours=2, weather_code=61)
    payload[section]['weather_code'] = value
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload),
    )) as http:
        fetched = await OpenMeteoClient(http).fetch(forecast_input())
    assert all(row.forecast_power_w == pytest.approx(3720) for row in fetched.intervals)
    assert [sample.weather_code for sample in fetched.weather_samples] == [None, None, None]
    assert [sample.air_temperature_c for sample in fetched.weather_samples] == [20, 20, 20]


@pytest.mark.parametrize('section', ['hourly', 'hourly_units'])
async def test_missing_optional_codes_leave_core_weather_available(section):
    payload = forecast_payload(0, hours=2, weather_code=61)
    del payload[section]['weather_code']
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload),
    )) as http:
        fetched = await OpenMeteoClient(http).fetch(forecast_input())
    assert fetched.intervals[0].forecast_power_w == pytest.approx(3720)
    assert all(sample.weather_code is None for sample in fetched.weather_samples)


async def test_quarter_hour_power_uses_minutely_inputs_and_weather_sampling_stays_hourly():
    payload = forecast_payload(10 * 3600, hours=1, weather_code=61)
    payload['hourly']['global_tilted_irradiance'] = [0, 0]
    payload['hourly']['temperature_2m'] = [10, 30]
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload),
    )) as http:
        batch = await OpenMeteoClient(http).fetch(forecast_input())
    interval = batch.intervals[0]
    assert (interval.start, interval.end) == (36000, 36900)
    assert (interval.end - interval.start, interval.cell_temperature_c) == (900, 45)
    assert interval.forecast_power_w == pytest.approx(3720)
    assert interval.forecast_energy_kwh == pytest.approx(0.93)
    assert batch.weather_samples[1].at - batch.weather_samples[0].at == 3600
    assert [sample.air_temperature_c for sample in batch.weather_samples] == [10, 30]
    assert [sample.irradiance_w_m2 for sample in batch.weather_samples] == [0, 0]
    assert [sample.weather_code for sample in batch.weather_samples] == [61, 61]


async def test_fetch_ambient_temperature_request():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            'minutely_15_units': {'time': 'unixtime', 'temperature_2m': '°C'},
            'minutely_15': {'time': [0, 900, 1800], 'temperature_2m': [21, None, 22.5]},
        })

    site = AmbientSite(latitude=31.2, longitude=121.5)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        observations = await OpenMeteoClient(http).fetch_ambient_temperature(site)

    request, = requests
    assert request.method == 'GET'
    assert (request.url.scheme, request.url.host, request.url.path) == ('https', 'api.open-meteo.com', '/v1/forecast')
    assert dict(request.url.params) == {
        'latitude': '31.2', 'longitude': '121.5', 'minutely_15': 'temperature_2m',
        'temperature_unit': 'celsius', 'timezone': 'UTC', 'timeformat': 'unixtime',
        'past_minutely_15': '672', 'forecast_minutely_15': '8',
    }
    assert 'authorization' not in request.headers and 'cookie' not in request.headers
    assert observations == (
        Observation(site.observation_entity_id, 0, 21),
        Observation(site.observation_entity_id, 900, None),
        Observation(site.observation_entity_id, 1800, 22.5),
    )


@pytest.mark.parametrize('changes', [
    {'minutely_15_units': {'time': 'unixtime', 'temperature_2m': '°F'}},
    {'minutely_15_units': {'time': 'iso8601', 'temperature_2m': '°C'}},
    {'minutely_15': {'time': [0, 1800], 'temperature_2m': [20, 21]}},
    {'minutely_15': {'time': [900, 900], 'temperature_2m': [20, 21]}},
    {'minutely_15': {'time': [0, 900], 'temperature_2m': [20]}},
    {'minutely_15': {'time': [0, float('inf')], 'temperature_2m': [20, 21]}},
])
async def test_ambient_temperature_rejects_invalid_units_or_timeline(changes):
    payload = {
        'minutely_15_units': {'time': 'unixtime', 'temperature_2m': '°C'},
        'minutely_15': {'time': [0, 900], 'temperature_2m': [20, 21]},
        **changes,
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=json.dumps(payload),
    ))) as http:
        with pytest.raises(ValueError):
            await OpenMeteoClient(http).fetch_ambient_temperature(AmbientSite(latitude=31.2, longitude=121.5))
