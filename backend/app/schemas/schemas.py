from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DecisionAction, MaintenanceRequestStatus, RiskCaseStatus


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


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


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_channel_id: int
    object_id: int | None
    device_id: int | None
    sensor_type: str
    location_tag: str | None
    display_name: str | None


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    risk_case_id: int | None
    model_version_id: int
    category: str
    probability: float
    window_start: dt.datetime
    window_end: dt.datetime
    threshold_used: float | None
    explanation: dict | None
    data_quality_flag: str | None
    created_at: dt.datetime


class RiskCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    category: str
    status: RiskCaseStatus
    priority: str | None
    opened_at: dt.datetime
    closed_at: dt.datetime | None


class DecisionIn(BaseModel):
    action: DecisionAction
    reason: str | None = None


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
    approved_at: dt.datetime | None


class TransitionIn(BaseModel):
    to_status: MaintenanceRequestStatus
    reason: str | None = None


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
