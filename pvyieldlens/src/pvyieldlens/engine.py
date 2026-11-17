from bisect import bisect_left, bisect_right
from dataclasses import dataclass, fields, replace
from itertools import accumulate

from .settings import MonitoringSettings


@dataclass(frozen=True)
class Observation:
    entity_id: str
    at: float
    value: float | None
    reported_at: float | None = None


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    estimated_power_w: float
    actual_power_w: float


@dataclass(frozen=True)
class WindowResult:
    start: float
    end: float
    valid_seconds: float
    estimated_energy_wh: float
    actual_energy_wh: float
    estimated_power_w: float | None
    actual_power_w: float | None
    pr: float | None
    optimizable_power_w: float | None
    data_completeness_percent: float
    quality: str
    reason: str | None
    segments: tuple[Segment, ...]

    def public(self):
        return {item.name: getattr(self, item.name) for item in fields(self) if item.name != "segments"}


def estimated_power(total_max_power_at_stc_w: float, pmax_temperature_coefficient_per_c: float, temperature_c: float,
                    irradiance_w_m2: float) -> float | None:
    temperature_correction_factor = 1 + pmax_temperature_coefficient_per_c * (temperature_c - 25)
    return total_max_power_at_stc_w * temperature_correction_factor * irradiance_w_m2 / 1000 if temperature_correction_factor >= 0 else None


def calculate(monitoring_settings: MonitoringSettings, observations: list[Observation], start: float, end: float) -> WindowResult:
    """Integrate the intersection of valid, piecewise constant source intervals."""
    sources = [sorted({item.at: item for item in observations if item.entity_id == entity and item.at < end}.values(),
                      key=lambda item: item.at) for entity in monitoring_settings.entities]
    points = sorted({start, end} | {
        point for source, age in zip(sources, monitoring_settings.max_ages)
        for item in source for point in (item.at, item.at + age) if start < point < end
    })
    segments = []
    coefficient = monitoring_settings.pmax_temperature_coefficient_per_c
    for left, right in zip(points, points[1:]):
        values = []
        for source, age in zip(sources, monitoring_settings.max_ages):
            index = bisect_right(source, left, key=lambda item: item.at) - 1
            item = source[index] if index >= 0 else None
            values.append(item.value if item and left < item.at + age else None)
        power, temperature, irradiance = values
        if power is None or temperature is None or irradiance is None:
            continue
        estimated = estimated_power(monitoring_settings.total_max_power_at_stc_w, coefficient, temperature, irradiance)
        if estimated is None:
            continue
        segments.append(Segment(left, right, estimated, power))
    duration = sum(part.end - part.start for part in segments)
    estimated = sum(part.estimated_power_w * (part.end - part.start) / 3600 for part in segments)
    actual = sum(part.actual_power_w * (part.end - part.start) / 3600 for part in segments)
    return _window_result(start, end, duration, estimated, actual, tuple(segments))


def _window_result(start: float, end: float, duration: float, estimated: float, actual: float,
                   segments: tuple[Segment, ...]) -> WindowResult:
    estimated_power_w = estimated * 3600 / duration if duration else None
    actual_power_w = actual * 3600 / duration if duration else None
    return WindowResult(
        start, end, duration, estimated, actual, estimated_power_w, actual_power_w,
        actual / estimated * 100 if estimated else None,
        estimated_power_w - actual_power_w if duration else None,
        duration / (end - start) * 100 if end > start else 0,
        "complete" if duration and abs(duration - (end - start)) < 1e-6 else "partial" if duration else "unavailable",
        "missing_data" if not duration else "zero_estimated_power" if not estimated else None,
        segments,
    )


def calculate_live(monitoring_settings: MonitoringSettings, observations: list[Observation], at: float, *,
                       started_at: float | None = None) -> WindowResult:
    result = calculate(monitoring_settings, observations, at - monitoring_settings.live_window_seconds, at)
    current = calculate(monitoring_settings, [item for item in observations if item.at <= at], at, at + 0.0001)
    return _live_result(result, bool(current.valid_seconds), started_at)


def _live_result(result: WindowResult, current_valid: bool, started_at: float | None) -> WindowResult:
    if not current_valid:
        return replace(result, estimated_power_w=None, actual_power_w=None, pr=None, optimizable_power_w=None,
                       quality='unavailable', reason='current_source_unavailable')
    if (result.quality == 'partial' and started_at is not None
            and started_at <= result.end < started_at + (result.end - result.start)):
        return replace(result, quality='warming_up')
    return result


def calculate_live_series(monitoring_settings: MonitoringSettings, observations: list[Observation], endpoints: list[float], *,
                              started_at: float | None = None) -> list[WindowResult]:
    """Reuse one integration for a request's rolling windows without retaining state."""
    if not endpoints:
        return []
    segments = calculate(monitoring_settings, observations, min(endpoints) - monitoring_settings.live_window_seconds,
                         max(endpoints) + 0.0001).segments
    starts = [part.start for part in segments]
    ends = [part.end for part in segments]
    durations = list(accumulate((part.end - part.start for part in segments), initial=0))
    estimated = list(accumulate((part.estimated_power_w * (part.end - part.start) / 3600 for part in segments), initial=0))
    actual = list(accumulate((part.actual_power_w * (part.end - part.start) / 3600 for part in segments), initial=0))
    results = []
    for at in endpoints:
        start = at - monitoring_settings.live_window_seconds
        left, right = bisect_right(ends, start), bisect_left(starts, at)
        parts = segments[left:right]
        duration = durations[right] - durations[left]
        estimated_wh = estimated[right] - estimated[left]
        actual_wh = actual[right] - actual[left]
        if parts and parts[0].start < start:
            clipped = start - parts[0].start
            duration -= clipped
            estimated_wh -= parts[0].estimated_power_w * clipped / 3600
            actual_wh -= parts[0].actual_power_w * clipped / 3600
            parts = (replace(parts[0], start=start), *parts[1:])
        if parts and parts[-1].end > at:
            clipped = parts[-1].end - at
            duration -= clipped
            estimated_wh -= parts[-1].estimated_power_w * clipped / 3600
            actual_wh -= parts[-1].actual_power_w * clipped / 3600
            parts = (*parts[:-1], replace(parts[-1], end=at))
        result = _window_result(start, at, duration, estimated_wh, actual_wh, parts)
        current = bisect_right(starts, at) - 1
        # As-of-at inputs cannot introduce a valid source later in the forward probe.
        current_valid = current >= 0 and at < ends[current]
        results.append(_live_result(result, current_valid, started_at))
    return results
