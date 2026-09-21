from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DecisionAction, MaintenanceRequestStatus, RiskCaseStatus, UserRole


class ObjectAccessIn(BaseModel):
    object_id: int = Field(description="Внутренний ID объекта", examples=[1])


class TokenOut(BaseModel):
    access_token: str = Field(description="JWT для заголовка Authorization: Bearer <access_token>")
    token_type: Literal["bearer"]
    role: UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool
    object_ids: list[int] = []


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    role: UserRole


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    role: str | None
    entity_type: str
    entity_id: int
    old_state: dict | None
    new_state: dict | None
    reason: str | None
    created_at: dt.datetime


class ChangePasswordIn(BaseModel):
    current_password: str = Field(description="Текущий пароль учётной записи")
    new_password: str = Field(min_length=8, description="Новый пароль, не короче 8 символов")


class ObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    parent_id: int | None
    name: str
    district: str | None
    kind: str | None
    geometry_wkt: str | None
    geometry_source: str | None


class DegradationTrendOut(BaseModel):
    """Динамика частоты "чистых" (не флаппинг) эпизодов неисправности канала — наблюдаемый
    факт по истории, НЕ прогноз износа оборудования (данных о возрасте/дате установки нет и
    не будет). См. docs/ТЗ_тренд_деградации_канала.md."""

    channel_id: int
    as_of: dt.datetime
    recent_window_days: int
    baseline_window_days: int
    recent_count: int
    baseline_count: int
    status: Literal["worsening", "stable", "improving", "insufficient_data"]


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_channel_id: int
    object_id: int | None
    device_id: int | None
    device_label: str | None = Field(
        default=None,
        description="Внешний ID физического устройства (например, «Н1-ПК440»), если канал сопоставлен",
    )
    sensor_type: str
    location_tag: str | None
    display_name: str | None
    degradation_trend: DegradationTrendOut | None = None


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    risk_case_id: int | None
    model_version_id: int
    category: str
    probability: float = Field(description="Вероятность отказа от 0 до 1", examples=[0.82])
    window_start: dt.datetime
    window_end: dt.datetime
    threshold_used: float | None = Field(description="Порог модели на момент расчёта", examples=[0.5])
    explanation: dict | None
    data_quality_flag: str | None
    created_at: dt.datetime
    llm_summary: str | None = None
    # Обогащение для «Журнала прогнозов» — узнаваемый номер канала (тот же, что на
    # «Рисках»/«Объектах»), а не внутренний PK.
    channel_external_id: int | None = None
    channel_label: str | None = None


class RiskCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    category: str
    status: RiskCaseStatus
    priority: str | None
    opened_at: dt.datetime
    closed_at: dt.datetime | None
    latest_probability: float | None = Field(
        default=None,
        description="Вероятность последнего прогноза от 0 до 1, если она включена в ответ",
        examples=[0.82],
    )
    channel_label: str | None = Field(
        default=None,
        description="Отображаемое имя канала или его внешний ID, если имя не задано",
    )
    channel_external_id: int | None = Field(
        default=None,
        description="Внешний ID канала (Channel.external_channel_id) — тот же, что показан в реестре каналов",
    )


class DecisionIn(BaseModel):
    action: DecisionAction = Field(
        description=(
            "observe — наблюдать; dispatch — направить на проверку; "
            "reject — отклонить; clarify — уточнить данные"
        ),
        examples=["observe"],
    )
    reason: str | None = Field(
        default=None,
        description="Комментарий к решению",
        examples=["Продолжить наблюдение за датчиком"],
    )


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_case_id: int
    user_id: int
    action: DecisionAction
    reason: str | None
    created_at: dt.datetime


class MaintenanceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_case_id: int
    work_type: str
    justification: str | None
    priority: str | None
    recommended_by: dt.datetime | None
    status: MaintenanceRequestStatus
    approved_by_user_id: int | None
    approved_by_username: str | None = None
    approved_at: dt.datetime | None
    created_at: dt.datetime
    # Обогащение для страницы «Заявки» (какой канал/объект/направление стоит за заявкой,
    # без необходимости отдельно открывать риск-кейс) — раздел «Заявки» админ-панели.
    category: str | None = None
    channel_label: str | None = None
    object_name: str | None = None
    # Дублирует резюме ИИ и сигнал «независимой модели» из риск-кейса под обоснование заявки,
    # и решение диспетчера (то, что он написал при переводе риска в dispatched) — раздел
    # «Заявки» иначе не показывал, почему заявка вообще возникла, без перехода в «Риски».
    ai_summary: str | None = None
    anomaly_is_outlier: bool | None = None
    dispatcher_username: str | None = None
    dispatcher_action: DecisionAction | None = None
    dispatcher_reason: str | None = None


class TransitionIn(BaseModel):
    to_status: MaintenanceRequestStatus = Field(
        description="Целевой статус, допустимый из текущего состояния заявки",
        examples=["in_progress"],
    )
    reason: str | None = Field(
        default=None,
        description="Комментарий к смене статуса",
        examples=["Специалист приступил к проверке"],
    )


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sensor_types: str
    trained_at: dt.datetime
    threshold: float | None
    metrics: dict | None
    is_active: bool


class HealthOut(BaseModel):
    status: str
