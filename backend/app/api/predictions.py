import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, Prediction, User
from app.schemas.schemas import PredictionOut
from app.services.llm_summary import generate_dispatcher_summary

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[Depends(get_current_user)])


def _apply_filters(stmt, channel_id, risk_case_id, category, since, until, search, accessible):
    # Один join на Channel и для search (внешний ID канала), и для матрицы доступа —
    # чтобы не подключать таблицу дважды в одном запросе.
    if search is not None or accessible is not None:
        stmt = stmt.join(Channel, Channel.id == Prediction.channel_id)
    if channel_id is not None:
        stmt = stmt.where(Prediction.channel_id == channel_id)
    if risk_case_id is not None:
        stmt = stmt.where(Prediction.risk_case_id == risk_case_id)
    if category is not None:
        stmt = stmt.where(Prediction.category == category)
    if since is not None:
        stmt = stmt.where(Prediction.created_at >= since)
    if until is not None:
        stmt = stmt.where(Prediction.created_at <= until)
    if search is not None:
        stmt = stmt.where(or_(Prediction.risk_case_id == search, Channel.external_channel_id == search))
    if accessible is not None:
        stmt = stmt.where(Channel.object_id.in_(accessible))
    return stmt


def _enrich(rows: list[Prediction], db: Session) -> list[PredictionOut]:
    """Название/внешний ID канала — чтобы в журнале был узнаваемый номер канала (тот же,
    что на «Рисках»/«Объектах»), а не внутренний PK, и можно было перейти на риск-кейс."""
    channel_ids = {p.channel_id for p in rows}
    channels = {c.id: c for c in db.scalars(select(Channel).where(Channel.id.in_(channel_ids)))} if channel_ids else {}
    out = []
    for p in rows:
        channel = channels.get(p.channel_id)
        out.append(
            PredictionOut(
                id=p.id,
                channel_id=p.channel_id,
                risk_case_id=p.risk_case_id,
                model_version_id=p.model_version_id,
                category=p.category,
                probability=p.probability,
                window_start=p.window_start,
                window_end=p.window_end,
                threshold_used=p.threshold_used,
                explanation=p.explanation,
                data_quality_flag=p.data_quality_flag,
                created_at=p.created_at,
                llm_summary=p.llm_summary,
                channel_external_id=channel.external_channel_id if channel else None,
                channel_label=channel.label if channel else None,
            )
        )
    return out


@router.get(
    "",
    response_model=list[PredictionOut],
    summary="Получить журнал прогнозов",
    description=(
        "Фильтры по каналу, риск-кейсу и категории; search — точное совпадение по ID риск-кейса "
        "или внешнему ID канала. since и until задают включительные границы created_at в ISO 8601. "
        "latest_per_case=true возвращает только последний прогноз каждого риск-кейса. sort_by: "
        "created_at или probability; sort_dir: asc или desc, по умолчанию новые/наибольшие первыми. "
        "Вероятность — число от 0 до 1. Учитывает доступ к объектам."
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
def list_predictions(
    response: Response,
    channel_id: int | None = None,
    risk_case_id: int | None = None,
    category: str | None = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    search: int | None = Query(None, description="Точное совпадение по ID риск-кейса или внешнему ID канала"),
    sort_by: Literal["created_at", "probability"] = "created_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    latest_per_case: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PredictionOut]:
    """Журнал прогнозов — неизменяемые записи (раздел 9.2 плана: «Журнал прогнозов»).

    `category` различает независимо оцениваемые треки (тема 18 CSV с ответами
    организаторов) — sensor_failure_pump_fan / sensor_failure_smoke_gas.

    `risk_case_id` — прогнозы конкретного риск-кейса (карточка риска, раздел «Почему
    сработал прогноз»): без него фильтр только по `channel_id`+`category` возвращал бы
    ПОСЛЕДНИЙ прогноз воркера по каналу вообще, даже если он относится к более новому,
    не связанному эпизоду, — для уже закрытого риск-кейса это показывало текущую (обычно
    другую) вероятность вместо той, что была при его открытии.

    `latest_per_case` — вместо сырого потока всех тиков (много почасовых записей на один
    и тот же риск-кейс, пока он открыт) вернуть только последний прогноз каждого риск-кейса
    (раздел «Журнал прогнозов» на фронте). Важно и не только для читаемости: массовый
    исторический импорт (`scripts/import_analysis_to_db.py`) не хранил признаки построчно —
    только итоговый score, поэтому реальный SHAP посчитан позже (`backfill_shap_explanations.py`)
    ТОЛЬКО для последнего прогноза каждого кейса (та же выборка, что открывает
    RiskCard.tsx). Без этого фильтра журнал в основном показывал старые тики с
    технической заглушкой в explanation вместо настоящего объяснения."""
    accessible = get_accessible_object_ids(user, db)

    if latest_per_case:
        dedup_stmt = _apply_filters(
            select(Prediction),
            channel_id,
            risk_case_id,
            category,
            since,
            until,
            search,
            accessible,
        )
        dedup_stmt = dedup_stmt.where(Prediction.risk_case_id.isnot(None)).distinct(
            Prediction.risk_case_id
        )
        # DISTINCT ON требует, чтобы ведущие столбцы ORDER BY совпадали с самим DISTINCT ON
        # (risk_case_id) — сортировка по выбору пользователя (sort_by/sort_dir) применяется
        # уже снаружи, к результату дедупликации, а не здесь.
        dedup_stmt = dedup_stmt.order_by(Prediction.risk_case_id, Prediction.created_at.desc())
        subq = dedup_stmt.subquery()

        count_stmt = select(func.count()).select_from(subq)
        response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

        prediction_alias = aliased(Prediction, subq)
        order_col = subq.c.probability if sort_by == "probability" else subq.c.created_at
        outer = (
            select(prediction_alias)
            .order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())
            .offset(offset)
            .limit(limit)
        )
        return _enrich(list(db.scalars(outer)), db)

    stmt = _apply_filters(select(Prediction), channel_id, risk_case_id, category, since, until, search, accessible)
    count_stmt = _apply_filters(
        select(func.count()).select_from(Prediction),
        channel_id,
        risk_case_id,
        category,
        since,
        until,
        search,
        accessible,
    )
    response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

    order_col = Prediction.probability if sort_by == "probability" else Prediction.created_at
    stmt = stmt.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())
    return _enrich(list(db.scalars(stmt.offset(offset).limit(limit))), db)


@router.get(
    "/{prediction_id}/summary",
    summary="Получить краткое резюме прогноза на естественном языке (для диспетчера)",
    description=(
        "Переводит SHAP-объяснение в 1-2 предложения человеческим языком. Считается лениво "
        "по первому запросу и кешируется в БД — повторные вызовы не дёргают LLM снова. "
        "Возвращает summary: null, если нет ключа стороннего API, нет объяснения для этого "
        "прогноза или запрос к LLM не удался — карточка риска не должна падать из-за этого."
    ),
    responses={
        403: {"description": "Нет доступа к объекту"},
        404: {"description": "Прогноз не найден"},
        401: {"description": "Требуется вход или токен недействителен"},
    },
)
def get_prediction_summary(
    prediction_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    prediction = db.get(Prediction, prediction_id)
    if prediction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогноз не найден")
    check_object_access(prediction.channel.object_id, user, db)

    if prediction.llm_summary is None:
        summary = generate_dispatcher_summary(prediction.explanation, prediction.probability)
        if summary is not None:
            prediction.llm_summary = summary
            db.commit()
    return {"summary": prediction.llm_summary}
