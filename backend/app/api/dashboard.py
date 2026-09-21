import datetime as dt
import os

from fastapi import APIRouter, Depends
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import (
    Channel,
    IncidentEpisode,
    MaintenanceRequest,
    ModelVersion,
    Object,
    Prediction,
    ReplayState,
    RiskCase,
    User,
)
from app.models.enums import RiskCaseStatus
from app.services.degradation_trend import compute_trend_for_channels

_TOP_WORSENING_LIMIT = 5

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])

_OPEN_STATUSES = (RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched)
# Раньше был захардкожен в 300с — ложно загорался красным каждый раз, когда
# REPLAY_SLEEP_SECONDS (пауза между тиками воркера) увеличивали выше этого порога (см.
# docs/Статус.md, инцидент 21 сентября: подняли до 365с, чтобы не наплодить риск-кейсов за
# неделю, — индикатор тут же стал "протухшим" между каждым тиком). Читаем ту же переменную
# окружения, что и сам воркер (app/workers/replay_worker.py), с запасом x2 + 60с на джиттер
# автозакрытия/сети — не тот же процесс, поэтому дублируем чтение env, а не импортируем
# константу напрямую (worker тянет тяжёлые catboost/pandas, недоступные в лёгком образе backend).
_WORKER_STALE_AFTER_SECONDS = int(os.environ.get("REPLAY_SLEEP_SECONDS", "2")) * 2 + 60
_DAILY_VOLUME_DAYS = 30


def _grouped_counts(db: Session, column, *filters) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).where(*filters).group_by(column)).all()
    return {(k.value if hasattr(k, "value") else str(k)): v for k, v in rows}


@router.get(
    "/summary",
    summary="Получить сводку по системе",
    description="Сводные показатели для обзора: риски, заявки, последние прогнозы и качество моделей.",
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
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

    # Открытые риск-кейсы, чей ПОСЛЕДНИЙ прогноз независимая модель (IsolationForest,
    # scripts/train_anomaly_model.py) пометила как аномальный — раздел «модели» админ-панели.
    # Смотрим только на последний прогноз каждого кейса (не «был ли аномальным хоть один из
    # всех прогнозов когда-либо») — иначе и семантически неверно (важно текущее состояние,
    # не вся история), и на выросшей таблице (10M+ строк) join по ВСЕМ прогнозам каждого
    # кейса с JSONB-фильтром на каждой строке — full nested loop, ~1.2 сек даже с индексами
    # (см. docs/Статус.md, инцидент 21 сентября 2026). Через «последний прогноз» —
    # ровно одна JSONB-проверка на кейс.
    latest_prediction_id = (
        select(Prediction.id)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )
    anomaly_flag = cast(Prediction.explanation, JSONB)["anomaly"]["is_outlier"].astext == "true"
    anomaly_stmt = (
        select(func.count())
        .select_from(RiskCase)
        .join(Prediction, Prediction.id == latest_prediction_id)
        .where(RiskCase.status.in_(_OPEN_STATUSES), anomaly_flag)
    )
    if accessible is not None:
        anomaly_stmt = anomaly_stmt.where(RiskCase.channel_id.in_(accessible_channel_ids))
    open_with_anomaly = db.scalar(anomaly_stmt) or 0

    models = list(db.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))))
    # По одному запросу на направление (их всего 2 — из уже посчитанного risk_by_category),
    # а не GROUP BY category по всей таблице: Postgres не умеет loose index scan, поэтому
    # общий GROUP BY по 10M+ строкам делал full scan (~1.4 сек), а точечный max(created_at)
    # WHERE category = X с индексом (category, created_at) — Index Scan Backward + LIMIT 1.
    last_prediction_by_category = {
        category: db.scalar(select(func.max(Prediction.created_at)).where(Prediction.category == category))
        for category in risk_by_category
    }

    # Индикатор живости воркера: replay_state.updated_at обновляется на каждом тике
    # (backend/app/workers/replay_worker.py) — не выдуманный «онлайн»-статус, а реальная
    # метка последней успешной записи в БД.
    replay_state = db.get(ReplayState, 1)
    worker_info = None
    if replay_state is not None:
        now = dt.datetime.now(dt.timezone.utc)
        seconds_since_update = (now - replay_state.updated_at).total_seconds()
        worker_info = {
            "virtual_time": replay_state.virtual_time,
            "updated_at": replay_state.updated_at,
            "seconds_since_update": round(seconds_since_update),
            "is_stale": seconds_since_update > _WORKER_STALE_AFTER_SECONDS,
        }

    # Опережает ли автозакрытие приток новых риск-кейсов — раздел «Обзор»: сколько кейсов
    # открывается и закрывается по дням (последние 30 дней данных). Не «сколько сейчас
    # открыто на дату X» (это потребовало бы дорогой посуточной реконструкции снимков), а
    # темп потока — если закрытий примерно столько же, сколько открытий, очередь не растёт
    # бесконтрольно.
    #
    # Точка отсчёта — max(opened_at) в самих данных, не datetime.now(): на выросшей таблице
    # (120k+ строк, часть дат виртуальная/историческая) агрегация БЕЗ границы по времени —
    # full scan всей таблицы (см. docs/Статус.md, инцидент 21 сентября 2026: /dashboard/summary
    # — 16.7 сек на проде). Граница отсекает 99%+ строк ДО group by, а не после.
    anchor_stmt = select(func.max(RiskCase.opened_at))
    if accessible is not None:
        anchor_stmt = anchor_stmt.where(RiskCase.channel_id.in_(accessible_channel_ids))
    anchor = db.scalar(anchor_stmt)

    if anchor is None:
        daily_volume = []
    else:
        window_start = anchor - dt.timedelta(days=_DAILY_VOLUME_DAYS + 1)
        opened_stmt = (
            select(func.date_trunc("day", RiskCase.opened_at).label("day"), func.count())
            .where(RiskCase.opened_at >= window_start)
            .group_by("day")
        )
        closed_stmt = (
            select(func.date_trunc("day", RiskCase.closed_at).label("day"), func.count())
            .where(RiskCase.closed_at >= window_start)
            .group_by("day")
        )
        if accessible is not None:
            opened_stmt = opened_stmt.where(RiskCase.channel_id.in_(accessible_channel_ids))
            closed_stmt = closed_stmt.where(RiskCase.channel_id.in_(accessible_channel_ids))
        opened_by_day = dict(db.execute(opened_stmt).all())
        closed_by_day = dict(db.execute(closed_stmt).all())
        all_days = sorted(set(opened_by_day) | set(closed_by_day))[-_DAILY_VOLUME_DAYS:]
        daily_volume = [
            {
                "date": day.date().isoformat(),
                "opened": opened_by_day.get(day, 0),
                "closed": closed_by_day.get(day, 0),
            }
            for day in all_days
        ]

    # Топ-5 каналов с растущей частотой "чистых" эпизодов — доп. сигнал внутри «Отказ
    # датчика», не «Износ инфраструктуры» (см. docs/ТЗ_тренд_деградации_канала.md, раздел
    # 5.2.3). Кандидаты — каналы, у которых вообще есть хоть один не-флаппинг эпизод
    # (иначе тренд для них всегда insufficient_data и они не полезны в топе).
    candidate_channels_stmt = (
        select(IncidentEpisode.channel_id).where(IncidentEpisode.is_flapping_incident.is_(False)).distinct()
    )
    if accessible is not None:
        candidate_channels_stmt = candidate_channels_stmt.where(
            IncidentEpisode.channel_id.in_(accessible_channel_ids)
        )
    candidate_channel_ids = list(db.scalars(candidate_channels_stmt))
    trends = compute_trend_for_channels(db, candidate_channel_ids)
    worsening = [
        {"channel_id": cid, **t}
        for cid, t in trends.items()
        if t["status"] == "worsening"
    ]
    worsening.sort(key=lambda t: t["recent"] - t["baseline"], reverse=True)
    top_worsening = worsening[:_TOP_WORSENING_LIMIT]
    channel_labels = {
        c.id: (c.display_name or f"Канал {c.external_channel_id}")
        for c in db.scalars(select(Channel).where(Channel.id.in_([t["channel_id"] for t in top_worsening])))
    }
    top_worsening_channels = [
        {
            "channel_id": t["channel_id"],
            "label": channel_labels.get(t["channel_id"], f"Канал #{t['channel_id']}"),
            "recent_count": t["recent"],
            "baseline_count": t["baseline"],
        }
        for t in top_worsening
    ]

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
        "worker": worker_info,
        "daily_volume": daily_volume,
        "top_worsening_channels": top_worsening_channels,
    }
