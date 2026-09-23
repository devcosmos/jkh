import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, cast, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, selectinload

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Channel, Decision, Prediction, RiskCase, User
from app.models.enums import RiskCaseStatus, UserRole
from app.schemas.schemas import DecisionIn, DecisionOut, RiskCaseOut
from app.services.maintenance_requests import ensure_request_for_dispatch

router = APIRouter(prefix="/risk-cases", tags=["risks"], dependencies=[Depends(get_current_user)])

# Порядок хода риск-кейса для сортировки по статусу (не алфавитный — тот же приём, что
# _STATUS_ORDER в maintenance_requests.py) и по серьёзности для приоритета.
_STATUS_ORDER = case(
    (RiskCase.status == RiskCaseStatus.new, 0),
    (RiskCase.status == RiskCaseStatus.observing, 1),
    (RiskCase.status == RiskCaseStatus.dispatched, 2),
    (RiskCase.status == RiskCaseStatus.resolved, 3),
    (RiskCase.status == RiskCaseStatus.rejected, 4),
)
_PRIORITY_ORDER = case((RiskCase.priority == "high", 2), (RiskCase.priority == "medium", 1), else_=0)

# Те же «открытые» статусы, что и dashboard.py (open_by_priority/open_with_anomaly) — здесь
# нужны, чтобы ссылка с плашки «Открытых рисков» на «Обзоре» могла отфильтровать список одним
# status=open, без перечисления трёх статусов на фронте.
_OPEN_STATUSES = (RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched)


def _apply_risk_case_filters(
    s,
    *,
    status_filter: str | None,
    category: str | None,
    priority: str | None,
    has_anomaly: bool | None,
    latest_anomaly_flag,
    channel_id: int | None,
    opened_after: dt.datetime | None,
    after_id: int | None,
    object_channel_ids,
    search: int | None,
):
    """Общие фильтры списка риск-кейсов — используются и списком (list_risk_cases), и
    сводкой по статусам/приоритету всей отфильтрованной выборки (risk_case_counts), не
    только показанных на текущей странице 20 строк."""
    if status_filter == "open":
        s = s.where(RiskCase.status.in_(_OPEN_STATUSES))
    elif status_filter:
        s = s.where(RiskCase.status == status_filter)
    if category:
        s = s.where(RiskCase.category == category)
    if priority:
        s = s.where(RiskCase.priority == priority)
    if has_anomaly:
        s = s.where(latest_anomaly_flag == "true")
    if channel_id is not None:
        s = s.where(Channel.external_channel_id == channel_id)
    if opened_after is not None:
        if after_id is not None:
            s = s.where(tuple_(RiskCase.opened_at, RiskCase.id) > tuple_(opened_after, after_id))
        else:
            s = s.where(RiskCase.opened_at > opened_after)
    if object_channel_ids is not None:
        s = s.where(RiskCase.channel_id.in_(object_channel_ids))
    if search is not None:
        s = s.where(or_(RiskCase.id == search, Channel.external_channel_id == search))
    return s


@router.get(
    "",
    response_model=list[RiskCaseOut],
    summary="Получить список риск-кейсов",
    description=(
        "Фильтры по status, category, priority, has_anomaly (последний прогноз помечен независимой моделью как "
        "аномальный), channel_id (внешний ID канала — тот же, что показан в реестре "
        "каналов, не внутренний PK), object_id, opened_after (строго позже указанного момента; при "
        "нескольких риск-кейсах с одинаковым opened_at используйте вместе с after_id — иначе кейсы с "
        "opened_at, равным водоразделу, не будут исключены только по времени) "
        "и search (точный ID риск-кейса или внешний ID канала). "
        "Сортировка sort_by: opened_at, probability, id, channel (внешний ID канала), "
        "category, status (по ходу риска, не по алфавиту) или priority (high/medium/без "
        "приоритета); sort_dir: asc или desc. По умолчанию — новые первыми. Учитывает доступ "
        "к объектам."
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
def list_risk_cases(
    response: Response,
    status_filter: str | None = Query(
        None, alias="status", description="Значение RiskCaseStatus, либо 'open' — алиас для new+observing+dispatched"
    ),
    category: str | None = None,
    priority: str | None = None,
    has_anomaly: bool | None = Query(
        None, description="Только риск-кейсы, чей последний прогноз помечен независимой моделью как аномальный"
    ),
    channel_id: int | None = None,
    object_id: int | None = None,
    opened_after: dt.datetime | None = Query(
        None, description="Только риск-кейсы, открытые строго позже этого момента (для поллинга новых)"
    ),
    after_id: int | None = Query(
        None,
        description=(
            "Тай-брейк для opened_after: ID последнего просмотренного риск-кейса. Без него несколько "
            "риск-кейсов с одинаковым opened_at (один и тот же тик replay) за пределами limit одного "
            "опроса никогда не попадают ни в один следующий ответ — строгое сравнение по одному opened_at "
            "исключает и уже показанные, и ещё не показанные кейсы с тем же временем одинаково."
        ),
    ),
    search: int | None = Query(None, description="Точное совпадение по ID риск-кейса или внешнему ID канала"),
    sort_by: Literal["opened_at", "probability", "id", "channel", "category", "status", "priority"] = "opened_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RiskCaseOut]:
    if status_filter and status_filter != "open" and status_filter not in RiskCaseStatus.__members__:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Некорректный статус: {status_filter}")

    # Вероятность последнего прогноза по риск-кейсу — не хранится на самом RiskCase (это
    # неизменяемый журнал Prediction, раздел 9.2 плана), поэтому вычисляется здесь как
    # коррелированный подзапрос, а не отдельным N+1 обращением на строку.
    latest_probability = (
        select(Prediction.probability)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )

    # Тот же приём, что и latest_probability выше (и в dashboard.py open_with_anomaly):
    # скалярный подзапрос по ПОСЛЕДНЕМУ прогнозу кейса, не join по всей истории —
    # JSONB-фильтр на каждой из 10M+ строк был бы дорогим full scan.
    latest_anomaly_flag = (
        select(cast(Prediction.explanation, JSONB)["anomaly"]["is_outlier"].astext)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )

    object_channel_ids = (
        select(Channel.id).where(Channel.object_id == object_id).scalar_subquery()
        if object_id is not None
        else None
    )

    # channel_id — внешний ID канала (Channel.external_channel_id), не внутренний PK: тот же
    # номер, что показан в реестре каналов, чтобы ссылка "показать риски этого канала" и
    # список рисков оперировали одним и тем же видимым пользователю числом.
    def apply_filters(s):
        return _apply_risk_case_filters(
            s,
            status_filter=status_filter,
            category=category,
            priority=priority,
            has_anomaly=has_anomaly,
            latest_anomaly_flag=latest_anomaly_flag,
            channel_id=channel_id,
            opened_after=opened_after,
            after_id=after_id,
            object_channel_ids=object_channel_ids,
            search=search,
        )

    stmt = (
        select(RiskCase, latest_probability.label("probability"), Channel)
        .join(Channel, Channel.id == RiskCase.channel_id)
        .options(selectinload(Channel.device))
    )
    stmt = apply_filters(stmt)
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = stmt.where(Channel.object_id.in_(accessible))

    # Пагинация по всем страницам (не только "последние N") — раздел «Риски» и остальные
    # списки админки иначе показывали только первую страницу без способа посмотреть
    # остальное (см. docs/documentation/Технические_заметки.md, запись 21 сентября). Total считаем тем же набором
    # фильтров, но без join/order по вероятности (та нужна только для сортировки, не влияет
    # на количество строк) — отдельный дешёвый count(*) по RiskCase.
    count_stmt = select(func.count()).select_from(RiskCase).join(Channel, Channel.id == RiskCase.channel_id)
    count_stmt = apply_filters(count_stmt)
    if accessible is not None:
        count_stmt = count_stmt.where(Channel.object_id.in_(accessible))
    response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

    _SORT_COLUMNS = {
        "opened_at": RiskCase.opened_at,
        "probability": latest_probability,
        "id": RiskCase.id,
        "channel": Channel.external_channel_id,
        "category": RiskCase.category,
        "status": _STATUS_ORDER,
        "priority": _PRIORITY_ORDER,
    }
    order_col = _SORT_COLUMNS[sort_by]
    # RiskCase.id как вторичный ключ сортировки — обязателен для opened_after+after_id курсора:
    # несколько риск-кейсов одного тика replay делят opened_at, без стабильного порядка внутри
    # такой группы курсор мог бы пропустить или повторить строку между двумя опросами.
    id_col = RiskCase.id.desc() if sort_dir == "desc" else RiskCase.id.asc()
    stmt = stmt.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc(), id_col)

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    return [
        RiskCaseOut(
            id=rc.id,
            channel_id=rc.channel_id,
            category=rc.category,
            status=rc.status,
            priority=rc.priority,
            opened_at=rc.opened_at,
            closed_at=rc.closed_at,
            latest_probability=proba,
            channel_label=channel.label,
            channel_external_id=channel.external_channel_id,
        )
        for rc, proba, channel in rows
    ]


@router.get(
    "/counts",
    summary="Получить сводку по статусам/приоритету риск-кейсов",
    description=(
        "Те же фильтры, что и у списка риск-кейсов (кроме сортировки/пагинации), но счётчики "
        "по ВСЕЙ отфильтрованной выборке, а не только по показанной странице — плашки "
        "«Открытые/Критично/Аномалии/Новые» над списком иначе считали только по 20 строкам "
        "текущей страницы. Путь — /counts, не /stats: у части блокировщиков рекламы в "
        "браузере (EasyPrivacy и подобные списки) есть общее правило на URL с /stats как на "
        "аналитику — самый вероятный кандидат на инцидент 24 сентября 2026 (бэкенд отвечал "
        "верно и напрямую, и через прод-домен тем же curl, но плашки на «Рисках» у "
        "пользователя показывали 0 при рабочем «Обзоре», чей /dashboard/summary под то же "
        "правило не подпадает)."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def risk_case_counts(
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    priority: str | None = None,
    has_anomaly: bool | None = None,
    channel_id: int | None = None,
    object_id: int | None = None,
    search: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if status_filter and status_filter != "open" and status_filter not in RiskCaseStatus.__members__:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Некорректный статус: {status_filter}")

    latest_anomaly_flag = (
        select(cast(Prediction.explanation, JSONB)["anomaly"]["is_outlier"].astext)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )
    object_channel_ids = (
        select(Channel.id).where(Channel.object_id == object_id).scalar_subquery()
        if object_id is not None
        else None
    )

    def apply_filters(s):
        return _apply_risk_case_filters(
            s,
            status_filter=status_filter,
            category=category,
            priority=priority,
            has_anomaly=has_anomaly,
            latest_anomaly_flag=latest_anomaly_flag,
            channel_id=channel_id,
            opened_after=None,
            after_id=None,
            object_channel_ids=object_channel_ids,
            search=search,
        )

    accessible = get_accessible_object_ids(user, db)

    def count(*extra) -> int:
        s = select(func.count()).select_from(RiskCase).join(Channel, Channel.id == RiskCase.channel_id)
        s = apply_filters(s)
        for cond in extra:
            s = s.where(cond)
        if accessible is not None:
            s = s.where(Channel.object_id.in_(accessible))
        return db.scalar(s) or 0

    return {
        "open": count(RiskCase.status.in_(_OPEN_STATUSES)),
        "critical": count(RiskCase.priority == "high"),
        "anomaly": count(latest_anomaly_flag == "true"),
        "fresh": count(RiskCase.status == RiskCaseStatus.new),
    }


@router.get(
    "/{risk_case_id}",
    response_model=RiskCaseOut,
    summary="Получить риск-кейс по ID",
    description="Учитывает доступ к объекту.",
    responses={
        403: {
            "description": "Нет доступа к объекту",
        },
        404: {
            "description": "Риск-кейс не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def get_risk_case(
    risk_case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RiskCaseOut:
    rc = db.get(RiskCase, risk_case_id)
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск-кейс не найден")
    check_object_access(rc.channel.object_id, user, db)
    latest = (
        db.execute(
            select(Prediction.probability)
            .where(Prediction.risk_case_id == rc.id)
            .order_by(Prediction.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return RiskCaseOut(
        id=rc.id,
        channel_id=rc.channel_id,
        category=rc.category,
        status=rc.status,
        priority=rc.priority,
        opened_at=rc.opened_at,
        closed_at=rc.closed_at,
        latest_probability=latest,
        channel_label=rc.channel.label,
        channel_external_id=rc.channel.external_channel_id,
    )


@router.post(
    "/{risk_case_id}/decisions",
    response_model=DecisionOut,
    summary="Принять решение по риску",
    description=(
        "Доступно диспетчеру, аналитику и администратору с доступом к объекту. observe переводит "
        "риск в observing; dispatch — в dispatched и создаёт или связывает заявку; reject закрывает "
        "риск как rejected; clarify записывает запрос уточнения без смены статуса."
    ),
    responses={
        403: {
            "description": "Недостаточно прав или нет доступа к объекту",
        },
        404: {
            "description": "Риск-кейс не найден",
        },
        409: {
            "description": "Риск-кейс уже закрыт (resolved/rejected) — новое решение не требуется",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def add_decision(
    risk_case_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.analyst, UserRole.admin)),
) -> Decision:
    """Решение диспетчера. Прогноз и решение — разные сущности (раздел 9.1 плана)."""
    rc = db.get(RiskCase, risk_case_id)
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск-кейс не найден")
    check_object_access(rc.channel.object_id, user, db)

    # Терминальные статусы — resolved закрывается автоматически воркером (48ч без новых
    # предупреждений), rejected — самим диспетчером. В обоих случаях решать больше нечего;
    # без этой проверки API принял бы новое решение по уже закрытому кейсу (фронтенд прячет
    # форму, но прямой запрос всё равно дошёл бы до этой точки).
    if rc.status in (RiskCaseStatus.resolved, RiskCaseStatus.rejected):
        raise HTTPException(status.HTTP_409_CONFLICT, "Риск-кейс уже закрыт — новое решение не требуется")

    old_status = rc.status
    decision = Decision(risk_case_id=risk_case_id, user_id=user.id, action=payload.action, reason=payload.reason)
    db.add(decision)

    if payload.action.value == "reject":
        rc.status = RiskCaseStatus.rejected
        rc.closed_at = dt.datetime.now(dt.timezone.utc)
    elif payload.action.value == "dispatch":
        rc.status = RiskCaseStatus.dispatched
        # Единственный источник заявок — раньше решение диспетчера и заявка на обслуживание
        # были не связаны, «направить на проверку» ничего не создавало в «Заявках» (см.
        # docs/documentation/Технические_заметки.md). Идемпотентно.
        ensure_request_for_dispatch(db, rc, rc.channel, user, payload.reason)
    elif payload.action.value == "observe":
        rc.status = RiskCaseStatus.observing

    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role.value,
            entity_type="risk_case",
            entity_id=rc.id,
            old_state={"status": old_status.value},
            new_state={"status": rc.status.value},
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(decision)
    return decision
