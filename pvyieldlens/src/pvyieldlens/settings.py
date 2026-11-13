from typing import Annotated, Literal, Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EntityId = Annotated[str, Field(pattern=r"^sensor\.[a-z0-9_]+$")]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    rated_power_w: float = Field(gt=0, le=1_000_000_000)
    temperature_coefficient_pct_per_c: float = Field(ge=-5, le=5)
    power_entity: EntityId
    temperature_entity: EntityId
    irradiance_entity: EntityId
    interval_minutes: Literal[1, 5, 10] = 5
    realtime_window_seconds: int = Field(default=60, ge=10, le=3600)
    update_seconds: int = Field(default=5, ge=1, le=60)
    power_max_age_seconds: int = Field(default=300, ge=1, le=86400)
    temperature_max_age_seconds: int = Field(default=900, ge=1, le=86400)
    irradiance_max_age_seconds: int = Field(default=300, ge=1, le=86400)
    timezone: str = "UTC"

    @field_validator("power_entity", "temperature_entity", "irradiance_entity")
    @classmethod
    def reject_feedback(cls, value: str) -> str:
        if value.startswith("sensor.pvyieldlens_"):
            raise ValueError("output_entity_as_source")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("invalid_timezone")
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.update_seconds > self.realtime_window_seconds:
            raise ValueError("update_exceeds_window")
        if len(set(self.entities)) != 3:
            raise ValueError("duplicate_sources")
        return self

    @property
    def entities(self) -> tuple[str, str, str]:
        return self.power_entity, self.temperature_entity, self.irradiance_entity

    @property
    def max_ages(self) -> tuple[int, int, int]:
        return self.power_max_age_seconds, self.temperature_max_age_seconds, self.irradiance_max_age_seconds

    @property
    def coefficient_per_c(self) -> float:
        return self.temperature_coefficient_pct_per_c / 100


class ForecastSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    enabled: bool = False
    tilt_deg: float | None = Field(default=None, ge=0, le=90)
    azimuth_deg: float | None = Field(default=None, ge=0, lt=360)
    noct_c: float = Field(default=45.0, gt=20, le=80)

    @model_validator(mode="after")
    def require_enabled_geometry(self) -> Self:
        if self.enabled and (self.tilt_deg is None or self.azimuth_deg is None):
            raise ValueError("forecast_geometry_required")
        return self


class HALocation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True, frozen=True)

    origin: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    location_name: str | None = None
    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError("invalid_timezone")
        return value
