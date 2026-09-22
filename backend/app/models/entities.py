"""ORM-модели по разделу 7.3 плана реализации.

Упрощения для MVP (см. docs/documentation/Технические_заметки.md за 15 сентября 2026):
- Геометрия объекта хранится как nullable WKT-текст, а не PostGIS Geometry — в
  справочнике объектов сейчас нет ни одной координаты (95 объектов без геометрии),
  подключать PostGIS до появления реальных геоданных нет смысла. Переход на
  geoalchemy2.Geometry — прямая замена типа колонки, без изменения остальной схемы.
- `feature_snapshots` не хранится в Postgres: витрина признаков живёт в Parquet/DuckDB
  (см. ml/features/build_features.py) — это соответствует разделу 7.2 плана («ML-витрины» —
  отдельный слой, не оперативная БД).
- `devices` заполняется эвристически по имени канала (`scripts/data/link_channels_to_devices.py`,
  15 сентября 2026) — 87.8% покрытия насос/вентилятор, остальное осталось без устройства
  (нет надёжного паттерна в названии), поэтому `device_id` остаётся nullable.
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
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
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

    @property
    def device_label(self) -> str | None:
        """Внешний ID физического устройства — см. scripts/data/link_channels_to_devices.py."""
        return self.device.external_id if self.device is not None else None

    @property
    def label(self) -> str:
        """Отображаемое имя канала с реальной идентичностью устройства в скобках, если оно
        сопоставлено — вместо голого ID канала в заявках/карточках (раздел 10 плана)."""
        base = self.display_name or str(self.external_channel_id)
        return f"{base} ({self.device_label})" if self.device_label else base


class IncidentEpisode(Base, TimestampMixin):
    """Очищенный эпизод отказа — см. docs/documentation/label-policy.md и ml/features/build_episodes.py."""

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
    # index=True на status/opened_at/closed_at — без них /dashboard/summary и /risk-cases на
    # выросшей за время работы воркера таблице (120k+ строк) делают full scan (см.
    # docs/documentation/Технические_заметки.md, инцидент 21 сентября 2026: /dashboard/summary — 16.7 сек).
    status: Mapped[RiskCaseStatus] = mapped_column(Enum(RiskCaseStatus), default=RiskCaseStatus.new, index=True)
    priority: Mapped[str | None] = mapped_column(String(32))
    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), index=True
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    channel: Mapped[Channel] = relationship()
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="risk_case")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="risk_case")
    maintenance_requests: Mapped[list["MaintenanceRequest"]] = relationship(back_populates="risk_case")


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"
    __table_args__ = (
        # Обслуживает паттерн "последний прогноз по риск-кейсу" (risks.py: latest_probability,
        # dashboard.py: open_with_anomaly) без сортировки всех прогнозов кейса в памяти —
        # см. миграцию a1b2c3d4e5f6 и docs/documentation/Технические_заметки.md, инцидент 21 сентября 2026.
        #
        # DB-01 (analys_and_todo.md): порядок сортировки второй колонки должен буквально
        # совпадать с миграцией (created_at DESC) — plain "created_at" (ASC) даёт другой
        # физический индекс, alembic check находил расхождение схемы между ORM и БД, хотя
        # запросы всё ещё могли работать (Postgres умеет читать ASC-индекс в обратном
        # порядке) - несовпадающее определение маскировало бы будущий дрейф схемы.
        Index("ix_predictions_risk_case_id_created_at", "risk_case_id", text("created_at DESC")),
        Index("ix_predictions_category_created_at", "category", text("created_at DESC")),
    )

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
    # Краткое резюме для диспетчера на естественном языке по explanation — считается лениво
    # (по первому запросу карточки, не на каждый тик воркера) и кешируется здесь, чтобы не
    # дёргать LLM повторно на каждый повторный просмотр. См. app/services/llm_summary.py.
    llm_summary: Mapped[str | None] = mapped_column(Text)
    # Переопределяет TimestampMixin.created_at только для этой таблицы — добавляет index=True
    # (сама таблица растёт на порядки быстрее остальных: 8.7M+ строк, ORDER BY/MAX по
    # created_at без индекса — full scan, см. docs/documentation/Технические_заметки.md, инцидент 21 сентября 2026).
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), index=True
    )

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

    __table_args__ = (
        # Ловит гонку двух одновременных «направить на проверку» на одном риск-кейсе — см.
        # app/services/maintenance_requests.py:ensure_request_for_dispatch, которая делает
        # find-then-insert без блокировки. Совпадает с миграцией
        # 9cb5c6b99664_maintenance_request_dedup_index.py (там — источник истины для прод/дев
        # БД; здесь — чтобы тот же индекс появлялся и в тестовой схеме через create_all).
        Index(
            "ix_maintenance_requests_active_dedup",
            "risk_case_id",
            "work_type",
            unique=True,
            postgresql_where=text("status NOT IN ('rejected', 'cancelled')"),
        ),
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserObjectAccess(Base, TimestampMixin):
    """Минимальная матрица доступа по объектам (раздел 12 плана — полная матрица с
    подразделениями отложена как требование будущего пилота; здесь только явное назначение
    пользователь-объект). Если у пользователя нет ни одной записи, ограничение не действует
    (см. app.api.deps.get_accessible_object_ids) — не ломает пользователей, для которых
    доступ ещё не настроен."""

    __tablename__ = "user_object_access"
    __table_args__ = (UniqueConstraint("user_id", "object_id", name="uq_user_object_access"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id"), index=True)

    user: Mapped["User"] = relationship()
    object: Mapped[Object] = relationship()


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


class ChannelRetentionWatermark(Base):
    """Состояние последнего события канала, вытесненного 7-суточным retention из
    channel_events (см. ChannelEvent). Без него LAG(state) по оставшимся строкам теряет
    prev_state у самой старой сохранённой записи, и переход состояния на границе retention
    молча выпадает из n_transitions_* (обнаружено scripts/maintenance/check_worker_feature_parity.py —
    воркер систематически недосчитывал ровно один переход, когда он случался на границе)."""

    __tablename__ = "channel_retention_watermark"

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    last_pruned_state: Mapped[str] = mapped_column(String(32))
    last_pruned_event_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class ReplayState(Base):
    """Курсор воспроизведения истории — простая сохраняемая точка возобновления вместо
    брокера сообщений (раздел 3 ТЗ MVP: «простая сохраняемая очередь/таблица заданий»)."""

    __tablename__ = "replay_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    virtual_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc)
    )
