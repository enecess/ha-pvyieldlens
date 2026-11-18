from bisect import bisect_right

from pydantic import BaseModel, ConfigDict

from .engine import Observation
from .history import HistoryRange, history_view
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


def _input_averages(observations: list[Observation], entity: str, max_age: int,
                    windows: list[HistoryWindow]) -> list[float | None]:
    """Average each input over its own known duration, including a valid predecessor."""
    source = [item for item in observations if item.entity_id == entity]
    averages = []
    for window in windows:
        weighted = duration = 0.0
        index = max(0, bisect_right(source, window['start'], key=lambda item: item.at) - 1)
        while index < len(source) and source[index].at < window['end']:
            item = source[index]
            right = min(window['end'], item.at + max_age,
                        source[index + 1].at if index + 1 < len(source) else window['end'])
            known = max(0, right - max(window['start'], item.at))
            if item.value is not None:
                weighted += item.value * known
                duration += known
            index += 1
        averages.append(weighted / duration if duration else None)
    return averages


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
            observations = store.observations(windows[0]['start'], windows[-1]['end'], config.entities, period.origin)
            irradiance = _input_averages(observations, config.irradiance_entity,
                                         config.irradiance_max_age_seconds, windows)
            temperature = (_input_averages(observations, config.module_temperature_entity,
                                           config.module_temperature_max_age_seconds, windows)
                           if config.module_temperature_entity is not None else [None] * len(windows))
            inputs.extend(GenerationInputPoint(start=window['start'], end=window['end'],
                                               irradiance_w_m2=sun, module_temperature_c=temp)
                          for window, sun, temp in zip(windows, irradiance, temperature))
    else:
        end = now
    return GenerationView(windows=history.windows, inputs=sorted(inputs, key=lambda point: point.start),
                          requested_range=HistoryRange(start=history.requested_range.start, end=end),
                          home_timezone=home_timezone)
