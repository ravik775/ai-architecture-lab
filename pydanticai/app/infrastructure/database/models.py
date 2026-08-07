"""SQLAlchemy 2.0 ORM models - the 5 tables from the persistence design."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CountryRow(Base):
    __tablename__ = "countries"

    country_code: Mapped[str] = mapped_column(String(2), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StateRow(Base):
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(
        String(2), ForeignKey("countries.country_code"), nullable=False
    )
    state_code: Mapped[str] = mapped_column(String(10), nullable=False)
    state_name: Mapped[str] = mapped_column(String(100), nullable=False)
    representative_location_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("configured_locations.location_id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("country_code", "state_code", name="uq_states_country_state"),
    )


class ConfiguredLocationRow(Base):
    __tablename__ = "configured_locations"

    location_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    location_name: Mapped[str] = mapped_column(String(150), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(2), ForeignKey("countries.country_code"), nullable=False
    )
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_preference: Mapped[str] = mapped_column(String(30), nullable=False, default="open_meteo")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_collection_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_state_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeatherObservationRow(Base):
    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("configured_locations.location_id"), nullable=False
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    observation_timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    apparent_temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_percent: Mapped[float] = mapped_column(Float, nullable=False)
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False)
    weather_code: Mapped[int] = mapped_column(Integer, nullable=False)
    wind_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_system: Mapped[str] = mapped_column(String(20), nullable=False, default="metric")
    collection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "location_id",
            "observation_date",
            "provider",
            "collection_type",
            name="uq_observation_idempotency",
        ),
    )


class UserRow(Base):
    """Minimal demo-grade user store for JWT auth/RBAC - see
    app/security/passwords.py and app/security/jwt_tokens.py. `role` is a
    free-form string, not a foreign-keyed roles table: this app has exactly
    one role that matters operationally (`force_trace_role`, default
    "trace_admin" - see sampling.py), not a real permissions model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyCollectionRunRow(Base):
    __tablename__ = "daily_collection_runs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_location_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON-encoded list of {location_id, error}, capped at N entries by BatchService.
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
