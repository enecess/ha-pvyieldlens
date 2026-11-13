import json

import httpx
import pytest
from pydantic import JsonValue

from pvyieldlens.open_meteo import OpenMeteoClient
from forecast_fixtures import forecast_input, hourly_payload


@pytest.mark.parametrize('azimuth_deg,provider_azimuth', [(0, -180), (90, -90), (180, 0), (270, 90)])
@pytest.mark.parametrize('latitude,longitude,tilt_deg', [(0, 0, 0), (31.2, 121.5, 25), (-33.9, -70.7, 90)])
async def test_request_uses_only_forecast_inputs(azimuth_deg, provider_azimuth, latitude, longitude, tilt_deg):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=hourly_payload(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = OpenMeteoClient(http=http)
        intervals = await client.fetch(forecast_input(
            latitude=latitude, longitude=longitude, tilt_deg=tilt_deg, azimuth_deg=azimuth_deg,
            origin='http://ha.test/private', timezone='Asia/Shanghai',
        ))
    request, = requests
    assert request.method == 'GET'
    assert (request.url.scheme, request.url.host, request.url.path) == ('https', 'api.open-meteo.com', '/v1/forecast')
    assert set(request.url.params) == {
        'latitude', 'longitude', 'tilt', 'azimuth', 'hourly', 'temperature_unit',
        'timezone', 'timeformat', 'past_days', 'forecast_days',
    }
    assert float(request.url.params['latitude']) == latitude
    assert float(request.url.params['longitude']) == longitude
    assert float(request.url.params['tilt']) == tilt_deg
    assert float(request.url.params['azimuth']) == provider_azimuth
    assert request.url.params['hourly'] == 'global_tilted_irradiance,temperature_2m'
    assert request.url.params['temperature_unit'] == 'celsius'
    assert request.url.params['timezone'] == 'UTC'
    assert request.url.params['timeformat'] == 'unixtime'
    assert (request.url.params['past_days'], request.url.params['forecast_days']) == ('1', '8')
    assert 'authorization' not in request.headers
    assert request.extensions['timeout'] == {'connect': 20, 'read': 20, 'write': 20, 'pool': 20}
    assert len(intervals) == 216


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
        return await client.fetch(forecast_input())


async def test_backward_mean_and_temperature_alignment():
    payload = hourly_payload(0)
    payload['hourly']['global_tilted_irradiance'][:3] = [None, 800, 400]
    payload['hourly']['temperature_2m'][:3] = [10, 30, 10]
    intervals = await fetch_payload(payload)
    assert len(intervals) == 216
    first, second = intervals[:2]
    assert (first.start, first.end, first.poa_w_m2, first.air_temperature_c) == (0, 3600, 800, 20)
    assert first.cell_temperature_c == 45
    assert first.power_w == pytest.approx(3720)
    assert first.energy_kwh == pytest.approx(3.72)
    assert (second.start, second.end, second.poa_w_m2, second.air_temperature_c) == (3600, 7200, 400, 20)
    assert second.cell_temperature_c == 32.5
    assert second.power_w == pytest.approx(1947.5)
    assert second.energy_kwh == pytest.approx(1.9475)
    assert (intervals[-1].start, intervals[-1].end) == (774000, 777600)


async def test_null_is_not_night_zero():
    payload = hourly_payload(0, hours=3)
    payload['hourly']['global_tilted_irradiance'] = [800, None, 0, 800]
    missing, night, daylight = await fetch_payload(payload)
    assert (missing.start, missing.end, missing.poa_w_m2, missing.power_w, missing.energy_kwh) == (0, 3600, None, None, None)
    assert missing.quality == 'unavailable'
    assert (night.start, night.end, night.poa_w_m2, night.power_w, night.energy_kwh) == (3600, 7200, 0, 0, 0)
    assert night.quality == 'complete'
    assert daylight.power_w == pytest.approx(3720)
    assert daylight.quality == 'complete'


@pytest.mark.parametrize('value', [None, -1, float('nan'), float('inf'), float('-inf'), '800', True, {}, []])
async def test_invalid_poa_keeps_interval_position(value):
    payload = hourly_payload(0, hours=3)
    payload['hourly']['global_tilted_irradiance'][2] = value
    intervals = await fetch_payload(payload)
    assert len(intervals) == 3
    assert (intervals[1].start, intervals[1].end, intervals[1].poa_w_m2) == (3600, 7200, None)
    assert intervals[1].power_w is intervals[1].energy_kwh is None
    assert intervals[1].quality == 'unavailable'
    assert intervals[0].power_w == intervals[2].power_w == pytest.approx(3720)


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), float('-inf'), '20', False, {}, []])
async def test_invalid_temperature_keeps_affected_intervals(value):
    payload = hourly_payload(0, hours=3)
    payload['hourly']['temperature_2m'][1] = value
    intervals = await fetch_payload(payload)
    assert len(intervals) == 3
    assert [(row.start, row.end) for row in intervals] == [(0, 3600), (3600, 7200), (7200, 10800)]
    assert [row.air_temperature_c for row in intervals] == [None, None, 20]
    assert [row.quality for row in intervals] == ['unavailable', 'unavailable', 'complete']
    assert intervals[0].power_w is intervals[1].power_w is None
    assert intervals[2].power_w == pytest.approx(3720)


async def test_negative_air_temperature_remains_valid():
    row, = await fetch_payload(hourly_payload(0, hours=1, air_temperature_c=-10))
    assert row.air_temperature_c == -10
    assert row.cell_temperature_c == 15
    assert row.power_w == pytest.approx(4140)
    assert row.quality == 'complete'


@pytest.mark.parametrize('section,field,value', [
    ('hourly', 'time', [0, 0, 7200]),
    ('hourly', 'time', [0, 7200, 3600]),
    ('hourly', 'time', [0, 1800, 3600]),
    ('hourly', 'time', [0, 3600, float('nan')]),
    ('hourly', 'time', [0, 3600, float('inf')]),
    ('hourly', 'time', [0, 3600, float('-inf')]),
    ('hourly', 'time', [0, 3600, None]),
    ('hourly', 'time', [0, 3600, '7200']),
    ('hourly', 'time', [False, 3600, 7200]),
    ('hourly', 'time', []),
    ('hourly', 'time', {}),
    ('hourly', 'global_tilted_irradiance', [800, 800]),
    ('hourly', 'global_tilted_irradiance', None),
    ('hourly', 'temperature_2m', [20, 20, 20, 20]),
    ('hourly', 'temperature_2m', '20'),
    ('hourly_units', 'global_tilted_irradiance', 'W/m2'),
    ('hourly_units', 'global_tilted_irradiance', None),
    ('hourly_units', 'temperature_2m', '°F'),
])
async def test_malformed_batch_is_rejected(section, field, value):
    payload = hourly_payload(0, hours=2)
    payload[section][field] = value
    with pytest.raises(ValueError):
        await fetch_payload(payload)


@pytest.mark.parametrize('section,field', [
    ('hourly', 'time'), ('hourly', 'global_tilted_irradiance'), ('hourly', 'temperature_2m'),
    ('hourly_units', 'global_tilted_irradiance'), ('hourly_units', 'temperature_2m'),
])
async def test_required_response_field_is_rejected_when_missing(section, field):
    payload = hourly_payload(0)
    del payload[section][field]
    with pytest.raises(ValueError):
        await fetch_payload(payload)


@pytest.mark.parametrize('payload', [None, [], 'weather', {}, {'hourly': []}, hourly_payload(0, hours=0)])
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
