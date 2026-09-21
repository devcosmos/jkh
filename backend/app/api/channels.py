from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, IncidentEpisode, User
from app.schemas.schemas import ChannelOut, DegradationTrendOut
from app.services.degradation_trend import (
    BASELINE_WINDOW_DAYS,
    RECENT_WINDOW_DAYS,
    compute_trend_for_channel,
    compute_trend_for_channels,
)

router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(get_current_user)])


def _trend_out(channel_id: int, trend: dict) -> DegradationTrendOut:
    return DegradationTrendOut(
        channel_id=channel_id,
        as_of=trend["as_of"],
        recent_window_days=RECENT_WINDOW_DAYS,
        baseline_window_days=BASELINE_WINDOW_DAYS,
        recent_count=trend["recent"],
        baseline_count=trend["baseline"],
        status=trend["status"],
    )


@router.get(
    "",
    response_model=list[ChannelOut],
    summary="Получить список каналов",
    description=(
        "Фильтры по объекту, типу датчика и поисковой строке (название или расположение). "
        "include_trend=true добавляет динамику частоты неисправностей. Учитывает доступ к объектам."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        200: {
            "description": "Страница записей",
            "headers": {
                "X-Total-Count": {
                    "description": "Всего записей с учётом фильтров, до limit и offset",
                    "schema": {
                        "type": "integer",
                    },
                },
            },
        },
    },
)
def list_channels(
    response: Response,
    object_id: int | None = None,
    sensor_type: str | None = None,
    search: str | None = None,
    include_trend: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Channel]:
    """Реестр каналов — раздел «Объекты и каналы» админ-панели, отдельно от иерархической
    схемы рисков (объекты/tree): здесь плоский список для поиска/инвентаризации."""
    stmt = select(Channel).options(selectinload(Channel.device))
    if object_id is not None:
        stmt = stmt.where(Channel.object_id == object_id)
    if sensor_type:
        stmt = stmt.where(Channel.sensor_type == sensor_type)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Channel.display_name.ilike(pattern), Channel.location_tag.ilike(pattern))
        )
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = stmt.where(Channel.object_id.in_(accessible))

    count_stmt = select(func.count()).select_from(Channel)
    if object_id is not None:
        count_stmt = count_stmt.where(Channel.object_id == object_id)
    if sensor_type:
        count_stmt = count_stmt.where(Channel.sensor_type == sensor_type)
    if search:
        pattern = f"%{search}%"
        count_stmt = count_stmt.where(
            or_(Channel.display_name.ilike(pattern), Channel.location_tag.ilike(pattern))
        )
    if accessible is not None:
        count_stmt = count_stmt.where(Channel.object_id.in_(accessible))
    response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

    stmt = stmt.order_by(Channel.id)
    channels = list(db.scalars(stmt.offset(offset).limit(limit)))

    if include_trend and channels:
        # Батч-запрос на всю уже отфильтрованную/пагинированную страницу — не по одному
        # каналу (см. docs/ТЗ_тренд_деградации_канала.md, раздел 5.2.2). Не считается по
        # умолчанию — лишняя нагрузка, если фронту не нужно.
        trends = compute_trend_for_channels(db, [c.id for c in channels])
        for c in channels:
            trend = trends.get(c.id)
            c.degradation_trend = _trend_out(c.id, trend) if trend else None

    return channels


@router.get(
    "/{channel_id}",
    response_model=ChannelOut,
    summary="Получить канал по ID",
    responses={
        404: {
            "description": "Канал не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def get_channel(channel_id: int, db: Session = Depends(get_db)) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Канал не найден")
    return ch


@router.get(
    "/{channel_id}/degradation-trend",
    response_model=DegradationTrendOut,
    summary="Получить динамику неисправностей канала",
    description=(
        "Сравнивает частоту эпизодов за недавний и базовый периоды. Статус: worsening, stable, "
        "improving или insufficient_data. Учитывает доступ к объекту."
    ),
    responses={
        403: {
            "description": "Нет доступа к объекту",
        },
        404: {
            "description": "Канал не найден или нет данных для расчёта тренда",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def get_channel_degradation_trend(
    channel_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DegradationTrendOut:
    """Доп. сигнал внутри «Отказ датчика» — динамика частоты эпизодов, не прогноз износа
    оборудования. См. docs/ТЗ_тренд_деградации_канала.md."""
    ch = db.get(Channel, channel_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Канал не найден")
    check_object_access(ch.object_id, user, db)

    trend = compute_trend_for_channel(db, channel_id)
    if trend is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Нет данных об эпизодах — тренд не может быть посчитан"
        )
    return _trend_out(channel_id, trend)


@router.get(
    "/{channel_id}/episodes",
    summary="Получить эпизоды неисправностей канала",
    description=(
        "История фактических неисправностей, от новых к старым. Содержит границы эпизодов и "
        "признаки флаппинга и неполных границ наблюдения."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def get_channel_episodes(channel_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Текущая/прошлая неисправность — отдельно от прогноза (раздел 9.1 плана)."""
    episodes = db.scalars(
        select(IncidentEpisode)
        .where(IncidentEpisode.channel_id == channel_id)
        .order_by(IncidentEpisode.start_time.desc())
    )
    return [
        {
            "id": e.id,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "is_flapping_incident": e.is_flapping_incident,
            "left_censored": e.left_censored,
            "right_censored": e.right_censored,
        }
        for e in episodes
    ]
