from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from .engine import Observation, input_spans, noct_temperature
from .history import HistoryRange, history_view
from .settings import MonitoringSettings
from .storage import HistoryWindow, Store


class GenerationInputPoint(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    start: float
    end: float
    irradiance_w_m2: float | None
    module_temperature_c: float | None


class GenerationView(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    windows: list[HistoryWindow]
    inputs: list[GenerationInputPoint]
    requested_range: HistoryRange
    home_timezone: str


def _generation_inputs(observations: list[Observation], config: MonitoringSettings,
                       windows: list[HistoryWindow]) -> Iterator[GenerationInputPoint]:
    """Clip one sequence of input spans to the ordered settlement windows."""
    sources = ((config.irradiance_entity, config.irradiance_max_age_seconds),)
    temperature_input = config.temperature_input
    if temperature_input is not None:
        sources = (*sources, temperature_input)
    noct = config.module_temperature_noct_c if config.module_temperature_entity is None else None
    spans = input_spans(observations, sources, windows[0]['start'], windows[-1]['end'])
    span = next(spans, None)
    for window in windows:
        start, end = window['start'], window['end']
        sun_total = sun_seconds = temperature_total = temperature_seconds = 0.0
        while span is not None and span[0] < end:
            left, right, values = span
            duration = min(end, right) - max(start, left)
            if duration > 0:
                sun = values[0]
                temperature = values[1] if temperature_input is not None else None
                if sun is not None:
                    sun_total += sun * duration
                    sun_seconds += duration
                if temperature is not None and noct is not None:
                    temperature = noct_temperature(temperature, sun, noct) if sun is not None else None
                if temperature is not None:
                    temperature_total += temperature * duration
                    temperature_seconds += duration
            if right > end:
                break
            span = next(spans, None)
        yield GenerationInputPoint(start=start, end=end,
                                   irradiance_w_m2=sun_total / sun_seconds if sun_seconds else None,
                                   module_temperature_c=temperature_total / temperature_seconds if temperature_seconds else None)


def generation_view(store: Store, now: float, home_timezone: str) -> GenerationView:
    """Read today's committed power and independent inputs under the service lock."""
    history = history_view(store, 'today', now, home_timezone)
    inputs = []
    if history.windows:
        grouped: dict[int, list[HistoryWindow]] = {}
        for window in history.windows:
            grouped.setdefault(window['revision'], []).append(window)
        end = max(window['end'] for window in history.windows)
        # A calendar fragment can retain a revision superseded before today's midnight.
        configurations = {period.revision: period for period in store.configuration_history(
            min(window.get('source_start', window['start']) for window in history.windows), end)}
        for revision, windows in grouped.items():
            period = configurations[revision]
            config = period.monitoring_settings
            observations = store.observations(windows[0]['start'], windows[-1]['end'],
                                              config.observation_entities, period.origin)
            inputs.extend(_generation_inputs(observations, config, windows))
    else:
        end = now
    return GenerationView(windows=history.windows, inputs=sorted(inputs, key=lambda point: point.start),
                          requested_range=HistoryRange(start=history.requested_range.start, end=end),
                          home_timezone=home_timezone)
