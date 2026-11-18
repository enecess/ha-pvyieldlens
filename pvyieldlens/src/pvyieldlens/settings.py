from typing import Annotated, Literal, Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EntityId = Annotated[str, Field(pattern=r"^sensor\.[a-z0-9_]+$")]
AngleEntityId = Annotated[str, Field(pattern=r"^(?:sensor|number|input_number)\.[a-z0-9_]+$")]
MonitoringRole = Literal['power', 'temperature', 'irradiance']
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
ModuleTemperatureNoct = Annotated[float, Field(gt=20, le=80)]
DEFAULT_NOCT_C = 45.0
AMBIENT_SAMPLE_SECONDS = 900
AMBIENT_OBSERVATION_PREFIX = 'weather:ambient:'


class AmbientSite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    latitude: Latitude
    longitude: Longitude

    @property
    def observation_entity_id(self) -> str:
        return f'{AMBIENT_OBSERVATION_PREFIX}{self.latitude or 0.0}:{self.longitude or 0.0}'


class MonitoringSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    total_max_power_at_stc_w: float = Field(gt=0, le=1_000_000_000)
    pmax_temperature_coefficient_pct_per_c: float = Field(ge=-5, le=5)
    actual_power_entity: EntityId
    module_temperature_entity: EntityId | None = None
    irradiance_entity: EntityId
    settlement_interval_minutes: Literal[1, 5, 10] = 5
    live_window_seconds: int = Field(default=60, ge=10, le=3600)
    update_interval_seconds: int = Field(default=5, ge=1, le=60)
    actual_power_max_age_seconds: int = Field(default=300, ge=1, le=86400)
    module_temperature_max_age_seconds: int = Field(default=900, ge=1, le=86400)
    irradiance_max_age_seconds: int = Field(default=300, ge=1, le=86400)
    home_timezone: str = "UTC"
    module_temperature_noct_c: ModuleTemperatureNoct = DEFAULT_NOCT_C
    ambient_site: AmbientSite | None = None

    @field_validator("actual_power_entity", "module_temperature_entity", "irradiance_entity")
    @classmethod
    def reject_feedback(cls, value: str | None) -> str | None:
        if value is not None and value.startswith("sensor.pvyieldlens_"):
            raise ValueError("output_entity_as_source")
        return value

    @field_validator("home_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("invalid_timezone")
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.update_interval_seconds > self.live_window_seconds:
            raise ValueError("update_exceeds_window")
        entities = self.entities
        if len(set(entities)) != len(entities):
            raise ValueError("duplicate_sources")
        return self

    @property
    def ha_sources(self) -> tuple[tuple[MonitoringRole, str, int], ...]:
        sources: tuple[tuple[MonitoringRole, str | None, int], ...] = (
            ('power', self.actual_power_entity, self.actual_power_max_age_seconds),
            ('temperature', self.module_temperature_entity, self.module_temperature_max_age_seconds),
            ('irradiance', self.irradiance_entity, self.irradiance_max_age_seconds),
        )
        return tuple((role, entity, max_age) for role, entity, max_age in sources if entity is not None)

    @property
    def entities(self) -> tuple[str, ...]:
        return tuple(entity for _, entity, _ in self.ha_sources)

    @property
    def max_ages(self) -> tuple[int, ...]:
        return tuple(max_age for _, _, max_age in self.ha_sources)

    @property
    def temperature_input(self) -> tuple[str, int] | None:
        if self.module_temperature_entity is not None:
            return self.module_temperature_entity, self.module_temperature_max_age_seconds
        if self.ambient_site is not None:
            return self.ambient_site.observation_entity_id, AMBIENT_SAMPLE_SECONDS
        return None

    @property
    def observation_entities(self) -> tuple[str, ...]:
        entities = self.entities
        temperature = self.temperature_input
        if self.module_temperature_entity is None and temperature is not None:
            return (*entities, temperature[0])
        return entities

    def public(self):
        return self.model_dump(exclude={'module_temperature_noct_c', 'ambient_site'})

    @property
    def pmax_temperature_coefficient_per_c(self) -> float:
        return self.pmax_temperature_coefficient_pct_per_c / 100


class ForecastSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    enabled: bool = False
    tilt_deg: float | None = Field(default=None, ge=0, le=90)
    azimuth_deg: float | None = Field(default=None, ge=0, lt=360)
    tilt_entity: AngleEntityId | None = None
    azimuth_entity: AngleEntityId | None = None
    noct_c: ModuleTemperatureNoct = DEFAULT_NOCT_C
    pr_history_days: int = Field(default=14, ge=3, le=90)

    @field_validator("tilt_entity", "azimuth_entity")
    @classmethod
    def reject_feedback(cls, value: str | None) -> str | None:
        if value is not None and value.startswith("sensor.pvyieldlens_"):
            raise ValueError("output_entity_as_source")
        return value

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        for fixed, entity in ((self.tilt_deg, self.tilt_entity), (self.azimuth_deg, self.azimuth_entity)):
            if fixed is not None and entity is not None:
                raise ValueError("forecast_angle_sources_conflict")
            if self.enabled and fixed is None and entity is None:
                raise ValueError("forecast_geometry_required")
        return self


class HALocation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    origin: str
    latitude: Latitude
    longitude: Longitude
    location_name: str | None = None
    home_timezone: str

    @field_validator("home_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("invalid_timezone")
        return value
