from fastapi import APIRouter, Depends
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, MaintenanceRequest, ModelVersion, Object, Prediction, RiskCase, User
from app.models.enums import RiskCaseStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])

_OPEN_STATUSES = (RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched)


def _grouped_counts(db: Session, column, *filters) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).where(*filters).group_by(column)).all()
    return {(k.value if hasattr(k, "value") else str(k)): v for k, v in rows}


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Обзорная сводка для стартовой страницы — агрегаты по уже существующим таблицам,
    без выдуманных метрик. Уважает матрицу доступа по объектам (см. get_accessible_object_ids),
    как и остальные эндпоинты."""
    accessible = get_accessible_object_ids(user, db)

    accessible_channel_ids = None
    accessible_risk_case_ids = None
    if accessible is not None:
        accessible_channel_ids = select(Channel.id).where(Channel.object_id.in_(accessible)).scalar_subquery()
        accessible_risk_case_ids = (
            select(RiskCase.id).where(RiskCase.channel_id.in_(accessible_channel_ids)).scalar_subquery()
        )

    rc_filters = [RiskCase.channel_id.in_(accessible_channel_ids)] if accessible is not None else []
    req_filters = (
        [MaintenanceRequest.risk_case_id.in_(accessible_risk_case_ids)] if accessible is not None else []
    )

    risk_by_status = _grouped_counts(db, RiskCase.status, *rc_filters)
    risk_by_category = _grouped_counts(db, RiskCase.category, *rc_filters)
    risk_open_by_priority = _grouped_counts(
        db, RiskCase.priority, RiskCase.status.in_(_OPEN_STATUSES), *rc_filters
    )
    total_open = sum(risk_open_by_priority.values())
    total_risk_cases = sum(risk_by_status.values())

    requests_by_status = _grouped_counts(db, MaintenanceRequest.status, *req_filters)

    # Топ объектов по собственному числу открытых риск-кейсов (без подъёма по иерархии —
    # полная агрегация уже есть в /objects/tree для схемы; здесь плоский рейтинг для дашборда).
    top_objects_stmt = (
        select(Object.id, Object.name, func.count(RiskCase.id).label("n"))
        .select_from(RiskCase)
        .join(Channel, Channel.id == RiskCase.channel_id)
        .join(Object, Object.id == Channel.object_id)
        .where(RiskCase.status.in_(_OPEN_STATUSES))
    )
    if accessible is not None:
        top_objects_stmt = top_objects_stmt.where(Object.id.in_(accessible))
    top_objects_stmt = (
        top_objects_stmt.group_by(Object.id, Object.name).order_by(func.count(RiskCase.id).desc()).limit(5)
    )
    top_objects = [
        {"object_id": oid, "name": name, "open_risk_count": n}
        for oid, name, n in db.execute(top_objects_stmt).all()
    ]

    # Открытые риск-кейсы, чей последний прогноз независимая модель (IsolationForest,
    # scripts/train_anomaly_model.py) пометила как аномальный — раздел «модели» админ-панели.
    anomaly_flag = cast(Prediction.explanation, JSONB)["anomaly"]["is_outlier"].astext == "true"
    anomaly_stmt = (
        select(func.count(func.distinct(RiskCase.id)))
        .select_from(RiskCase)
        .join(Prediction, Prediction.risk_case_id == RiskCase.id)
        .where(RiskCase.status.in_(_OPEN_STATUSES), anomaly_flag)
    )
    if accessible is not None:
        anomaly_stmt = anomaly_stmt.where(RiskCase.channel_id.in_(accessible_channel_ids))
    open_with_anomaly = db.scalar(anomaly_stmt) or 0

    models = list(db.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))))
    last_prediction_by_category = dict(
        db.execute(
            select(Prediction.category, func.max(Prediction.created_at)).group_by(Prediction.category)
        ).all()
    )

    return {
        "risk_cases": {
            "total": total_risk_cases,
            "total_open": total_open,
            "by_status": risk_by_status,
            "by_category": risk_by_category,
            "open_by_priority": risk_open_by_priority,
            "open_with_anomaly": open_with_anomaly,
        },
        "requests": {"by_status": requests_by_status},
        "top_objects": top_objects,
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "sensor_types": m.sensor_types,
                "threshold": m.threshold,
                "trained_at": m.trained_at,
                "roc_auc_test": (m.metrics or {}).get("roc_auc_test"),
                "target_met": (m.metrics or {}).get("target_met"),
            }
            for m in models
        ],
        "last_prediction_by_category": last_prediction_by_category,
    }
