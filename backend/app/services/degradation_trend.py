"""Тренд деградации канала — доп. сигнал внутри направления «Отказ датчика», не отдельное
направление «Износ инфраструктуры» (для него нет и не будет данных о возрасте оборудования,
см. docs/ТЗ_тренд_деградации_канала.md, раздел 1). Считает, растёт или падает частота
«чистых» (не флаппинг) эпизодов неисправности канала за последние 90 дней против
предыдущих 90 — наблюдаемый факт по истории, не прогноз физического износа.

Пороги (RECENT/BASELINE_WINDOW_DAYS, MIN_TOTAL_EPISODES, WORSENING/IMPROVING_RATIO,
MIN_ABSOLUTE_DELTA) — рабочая эвристика, ревизуемая, того же рода, что debounce/флаппинг-пороги
в docs/label-policy.md и MIN_BIN_SIZE в scripts/compute_calibration.py.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import IncidentEpisode

RECENT_WINDOW_DAYS = 90
BASELINE_WINDOW_DAYS = 90
MIN_TOTAL_EPISODES = 3
WORSENING_RATIO = 1.5
IMPROVING_RATIO = 0.67
MIN_ABSOLUTE_DELTA = 2

TrendStatus = Literal["worsening", "stable", "improving", "insufficient_data"]


def get_as_of(db: Session) -> dt.datetime | None:
    """Точка отсчёта — максимальная дата в самих данных, не datetime.now(): таблица
    incident_episodes наполняется только разовым импортом и не растёт со временем
    (см. docs/ТЗ_тренд_деградации_канала.md, раздел 2/3 — та же ловушка, что уже была
    в JournalPage.tsx с датой "устаревания")."""
    return db.scalar(select(func.max(IncidentEpisode.start_time)))


def _classify(recent: int, baseline: int) -> TrendStatus:
    total = recent + baseline
    if total < MIN_TOTAL_EPISODES:
        return "insufficient_data"
    if recent >= baseline * WORSENING_RATIO and recent - baseline >= MIN_ABSOLUTE_DELTA:
        return "worsening"
    if recent <= baseline * IMPROVING_RATIO and baseline - recent >= MIN_ABSOLUTE_DELTA:
        return "improving"
    return "stable"


def compute_trend_for_channels(db: Session, channel_ids: list[int]) -> dict[int, dict]:
    """Одним SQL-запросом (два условных COUNT(*) FILTER) для всех переданных channel_id —
    без N+1, по прецеденту _grouped_counts в app/api/dashboard.py. Возвращает
    {channel_id: {"as_of", "recent", "baseline", "status"}}; пустой словарь, если каналов
    нет или в таблице вовсе нет эпизодов (as_of is None)."""
    if not channel_ids:
        return {}

    as_of = get_as_of(db)
    if as_of is None:
        return {}

    recent_start = as_of - dt.timedelta(days=RECENT_WINDOW_DAYS)
    baseline_start = recent_start - dt.timedelta(days=BASELINE_WINDOW_DAYS)

    stmt = (
        select(
            IncidentEpisode.channel_id,
            func.count()
            .filter(IncidentEpisode.start_time > recent_start, IncidentEpisode.start_time <= as_of)
            .label("recent"),
            func.count()
            .filter(
                IncidentEpisode.start_time > baseline_start,
                IncidentEpisode.start_time <= recent_start,
            )
            .label("baseline"),
        )
        .where(
            IncidentEpisode.is_flapping_incident.is_(False),
            IncidentEpisode.channel_id.in_(channel_ids),
        )
        .group_by(IncidentEpisode.channel_id)
    )

    result: dict[int, dict] = {}
    for channel_id, recent, baseline in db.execute(stmt).all():
        result[channel_id] = {
            "as_of": as_of,
            "recent": recent,
            "baseline": baseline,
            "status": _classify(recent, baseline),
        }
    # Каналы без единого не-флаппинг эпизода в таблице не попадают в GROUP BY — заполняем
    # нулями явно, а не молчим: 0/0 — тоже insufficient_data, не отсутствие ответа.
    for channel_id in channel_ids:
        if channel_id not in result:
            result[channel_id] = {"as_of": as_of, "recent": 0, "baseline": 0, "status": "insufficient_data"}
    return result


def compute_trend_for_channel(db: Session, channel_id: int) -> dict | None:
    """Тренд по одному каналу — для карточки риска. None, только если в таблице вовсе нет
    эпизодов ни по одному каналу (as_of is None) — тогда сигнал не может быть посчитан
    в принципе."""
    return compute_trend_for_channels(db, [channel_id]).get(channel_id)
