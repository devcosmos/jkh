"""Расширенная аналитика — раздел 8 ЖКХ.md («Дополнительные требования», реализация
по согласованию с заказчиком, не блокирует MVP): детальная статистика по типам
инцидентов, сезонность, исторические отчёты по ремонтам. Три независимых агрегата,
используются и на веб-странице «Аналитика», и в экспортах XLSX/PDF (одни и те же
числа — не отдельная выдуманная логика для отчёта)."""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Channel, IncidentEpisode, MaintenanceRequest, Prediction, RiskCase
from app.models.enums import RiskCaseStatus

_OPEN_STATUSES = (RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched)

MONTH_NAMES_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def _channel_ids_subquery(accessible: set[int] | None):
    if accessible is None:
        return None
    return select(Channel.id).where(Channel.object_id.in_(accessible)).scalar_subquery()


def incident_type_breakdown(db: Session, accessible: set[int] | None) -> list[dict]:
    """Детальная статистика по типам инцидентов (раздел 8): по каждому типу датчика —
    сколько реальных эпизодов неисправности (без флаппинга), сколько риск-кейсов из них
    родилось, сколько сейчас открыто и средняя вероятность последнего прогноза."""
    channel_ids = _channel_ids_subquery(accessible)

    episode_stmt = (
        select(Channel.sensor_type, func.count(IncidentEpisode.id))
        .join(IncidentEpisode, IncidentEpisode.channel_id == Channel.id)
        .where(IncidentEpisode.is_flapping_incident.is_(False))
    )
    if channel_ids is not None:
        episode_stmt = episode_stmt.where(Channel.id.in_(channel_ids))
    episode_stmt = episode_stmt.group_by(Channel.sensor_type)
    episodes_by_type = dict(db.execute(episode_stmt).all())

    risk_stmt = (
        select(
            Channel.sensor_type,
            func.count(RiskCase.id),
            func.count(RiskCase.id).filter(RiskCase.status.in_(_OPEN_STATUSES)),
        )
        .join(RiskCase, RiskCase.channel_id == Channel.id)
    )
    if channel_ids is not None:
        risk_stmt = risk_stmt.where(Channel.id.in_(channel_ids))
    risk_stmt = risk_stmt.group_by(Channel.sensor_type)
    risk_by_type = {row[0]: (row[1], row[2]) for row in db.execute(risk_stmt).all()}

    latest_probability = (
        select(Prediction.probability)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )
    avg_stmt = (
        select(Channel.sensor_type, func.avg(latest_probability))
        .select_from(RiskCase)
        .join(Channel, Channel.id == RiskCase.channel_id)
        .where(RiskCase.status.in_(_OPEN_STATUSES))
    )
    if channel_ids is not None:
        avg_stmt = avg_stmt.where(Channel.id.in_(channel_ids))
    avg_stmt = avg_stmt.group_by(Channel.sensor_type)
    avg_prob_by_type = dict(db.execute(avg_stmt).all())

    sensor_types = set(episodes_by_type) | set(risk_by_type)
    return [
        {
            "sensor_type": st,
            "episode_count": episodes_by_type.get(st, 0),
            "risk_case_count": risk_by_type.get(st, (0, 0))[0],
            "open_risk_case_count": risk_by_type.get(st, (0, 0))[1],
            "avg_open_probability": round(float(avg_prob_by_type[st]), 3) if avg_prob_by_type.get(st) else None,
        }
        for st in sorted(sensor_types)
    ]


def seasonal_breakdown(db: Session, accessible: set[int] | None) -> list[dict]:
    """Прогнозная аналитика с учётом сезонных изменений (раздел 8): частота реальных
    эпизодов неисправности по календарному месяцу, агрегированная по всем годам данных —
    показывает, есть ли устойчивый сезонный паттерн (например, отопительный сезон)."""
    channel_ids = _channel_ids_subquery(accessible)
    month_col = func.extract("month", IncidentEpisode.start_time).label("month")
    stmt = (
        select(month_col, func.count(IncidentEpisode.id))
        .join(Channel, Channel.id == IncidentEpisode.channel_id)
        .where(IncidentEpisode.is_flapping_incident.is_(False))
    )
    if channel_ids is not None:
        stmt = stmt.where(Channel.id.in_(channel_ids))
    stmt = stmt.group_by(month_col)
    counts = {int(m): n for m, n in db.execute(stmt).all()}
    return [
        {"month": m, "month_name": MONTH_NAMES_RU[m - 1], "episode_count": counts.get(m, 0)}
        for m in range(1, 13)
    ]


def maintenance_history(db: Session, accessible: set[int] | None) -> dict:
    """Исторические отчёты по ремонтам (раздел 8): распределение заявок на обслуживание
    по виду работ и статусу, помесячная динамика создания и среднее время до утверждения."""
    risk_case_ids = None
    if accessible is not None:
        channel_ids = _channel_ids_subquery(accessible)
        risk_case_ids = select(RiskCase.id).where(RiskCase.channel_id.in_(channel_ids)).scalar_subquery()

    def _filtered(stmt):
        return stmt.where(MaintenanceRequest.risk_case_id.in_(risk_case_ids)) if risk_case_ids is not None else stmt

    by_work_type = dict(
        db.execute(_filtered(select(MaintenanceRequest.work_type, func.count())).group_by(MaintenanceRequest.work_type)).all()
    )
    by_status = {
        k.value: v
        for k, v in db.execute(
            _filtered(select(MaintenanceRequest.status, func.count())).group_by(MaintenanceRequest.status)
        ).all()
    }

    month_col = func.date_trunc("month", MaintenanceRequest.created_at).label("month")
    monthly_stmt = _filtered(select(month_col, func.count())).group_by(month_col).order_by(month_col)
    monthly = [
        {"month": m.strftime("%Y-%m"), "request_count": n} for m, n in db.execute(monthly_stmt).all() if m is not None
    ]

    avg_seconds_stmt = _filtered(
        select(func.avg(func.extract("epoch", MaintenanceRequest.approved_at - MaintenanceRequest.created_at)))
    ).where(MaintenanceRequest.approved_at.isnot(None))
    avg_seconds = db.scalar(avg_seconds_stmt)
    avg_hours_to_approval = round(float(avg_seconds) / 3600, 1) if avg_seconds else None

    return {
        "by_work_type": [{"work_type": k, "count": v} for k, v in sorted(by_work_type.items())],
        "by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "monthly": monthly,
        "avg_hours_to_approval": avg_hours_to_approval,
    }


def full_report(db: Session, accessible: set[int] | None) -> dict:
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "incident_types": incident_type_breakdown(db, accessible),
        "seasonal": seasonal_breakdown(db, accessible),
        "maintenance": maintenance_history(db, accessible),
    }
