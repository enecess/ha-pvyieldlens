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
    assert len(payloads) == 9
    assert payloads['sensor.pvyieldlens_pr']['state'] == 'unavailable'
    assert payloads['sensor.pvyieldlens_total_estimated_energy']['state'] == '1.2'


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
