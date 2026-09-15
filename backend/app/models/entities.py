"""ORM-модели по разделу 7.3 плана реализации.

Упрощения для MVP (см. docs/Статус.md за 15 сентября 2026):
- Геометрия объекта хранится как nullable WKT-текст, а не PostGIS Geometry — в
  справочнике объектов сейчас нет ни одной координаты (95 объектов без геометрии),
  подключать PostGIS до появления реальных геоданных нет смысла. Переход на
  geoalchemy2.Geometry — прямая замена типа колонки, без изменения остальной схемы.
- `feature_snapshots` не хранится в Postgres: витрина признаков живёт в Parquet/DuckDB
  (см. scripts/build_features.py) — это соответствует разделу 7.2 плана («ML-витрины» —
  отдельный слой, не оперативная БД).
- `devices` существует, но соответствие channel→device не установлено (открытый вопрос
  аудита данных) — device_id везде nullable, канал может существовать без устройства.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import (
    DecisionAction,
    EpisodeSource,
    MaintenanceRequestStatus,
    RiskCaseStatus,
    UserRole,
)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class Object(Base, TimestampMixin):
    __tablename__ = "objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id"))
    name: Mapped[str] = mapped_column(String(256))
    district: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str | None] = mapped_column(String(64))  # вид_объекта
    hierarchy_level: Mapped[int | None] = mapped_column(Integer)
    geometry_wkt: Mapped[str | None] = mapped_column(Text)  # см. упрощение выше
    geometry_source: Mapped[str | None] = mapped_column(String(64))

    channels: Mapped[list["Channel"]] = relationship(back_populates="object")


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    device_type: Mapped[str | None] = mapped_column(String(128))
    install_date: Mapped[dt.date | None] = mapped_column(DateTime)
    last_maintenance_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    channels: Mapped[list["Channel"]] = relationship(back_populates="device")


class Channel(Base, TimestampMixin):
    """Соответствует ид_канала_данных источника (справочник_каналов_датчиков.csv)."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_channel_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    sensor_type: Mapped[str] = mapped_column(String(128), index=True)  # тип_датчика
    subsystem: Mapped[str | None] = mapped_column(String(128))  # тип_инж_системы
    location_tag: Mapped[str | None] = mapped_column(String(128), index=True)  # тег_инженерной_системы
    location_group: Mapped[str | None] = mapped_column(String(128), index=True)  # см. label-policy: соседи
    display_name: Mapped[str | None] = mapped_column(String(256))
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    object: Mapped[Object | None] = relationship(back_populates="channels")
    device: Mapped[Device | None] = relationship(back_populates="channels")
    episodes: Mapped[list["IncidentEpisode"]] = relationship(back_populates="channel")


class IncidentEpisode(Base, TimestampMixin):
    """Очищенный эпизод отказа — см. docs/label-policy.md и scripts/build_episodes.py."""

    __tablename__ = "incident_episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    sensor_type: Mapped[str] = mapped_column(String(128))
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[EpisodeSource] = mapped_column(Enum(EpisodeSource), default=EpisodeSource.sensor_state)
    is_flapping_incident: Mapped[bool] = mapped_column(Boolean, default=False)
    left_censored: Mapped[bool] = mapped_column(Boolean, default=False)
    right_censored: Mapped[bool] = mapped_column(Boolean, default=False)
    label_policy_version: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)

    channel: Mapped[Channel] = relationship(back_populates="episodes")


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    sensor_types: Mapped[str] = mapped_column(String(256))  # через запятую, напр. "насос,вентилятор"
    trained_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    train_period_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    train_period_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    threshold: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="model_version")


class RiskCase(Base, TimestampMixin):
    __tablename__ = "risk_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    category: Mapped[str] = mapped_column(String(64), default="sensor_failure")
    status: Mapped[RiskCaseStatus] = mapped_column(Enum(RiskCaseStatus), default=RiskCaseStatus.new)
    priority: Mapped[str | None] = mapped_column(String(32))
    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped[Channel] = relationship()
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="risk_case")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="risk_case")
    maintenance_requests: Mapped[list["MaintenanceRequest"]] = relationship(back_populates="risk_case")


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    risk_case_id: Mapped[int | None] = mapped_column(ForeignKey("risk_cases.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    category: Mapped[str] = mapped_column(String(64), default="sensor_failure")
    probability: Mapped[float] = mapped_column(Float)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    threshold_used: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[dict | None] = mapped_column(JSON)
    data_quality_flag: Mapped[str | None] = mapped_column(String(32))  # ok / stale / insufficient

    channel: Mapped[Channel] = relationship()
    risk_case: Mapped[RiskCase | None] = relationship(back_populates="predictions")
    model_version: Mapped[ModelVersion] = relationship(back_populates="predictions")


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_case_id: Mapped[int] = mapped_column(ForeignKey("risk_cases.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[DecisionAction] = mapped_column(Enum(DecisionAction))
    reason: Mapped[str | None] = mapped_column(Text)

    risk_case: Mapped[RiskCase] = relationship(back_populates="decisions")
    user: Mapped["User"] = relationship()


class MaintenanceRequest(Base, TimestampMixin):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_case_id: Mapped[int] = mapped_column(ForeignKey("risk_cases.id"), index=True)
    work_type: Mapped[str] = mapped_column(String(128))
    justification: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(String(32))
    recommended_by: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MaintenanceRequestStatus] = mapped_column(
        Enum(MaintenanceRequestStatus), default=MaintenanceRequestStatus.draft
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    risk_case: Mapped[RiskCase] = relationship(back_populates="maintenance_requests")
    approved_by: Mapped["User | None"] = relationship()


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str | None] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(Integer)
    old_state: Mapped[dict | None] = mapped_column(JSON)
    new_state: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base, TimestampMixin):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running")
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64))


class ChannelEvent(Base):
    """Оперативный контур (раздел 7.2 плана): скользящее окно свежих событий для расчёта
    признаков в реальном времени. Не архив — старше окна максимального признака (7 суток)
    удаляется worker'ом, полная история остаётся в Parquet/DuckDB, а не здесь."""

    __tablename__ = "channel_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    event_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(32))
    is_alarm: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class ReplayState(Base):
    """Курсор воспроизведения истории — простая сохраняемая точка возобновления вместо
    брокера сообщений (раздел 3 ТЗ MVP: «простая сохраняемая очередь/таблица заданий»)."""

    __tablename__ = "replay_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    virtual_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc)
    )
