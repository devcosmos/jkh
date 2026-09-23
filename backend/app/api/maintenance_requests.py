import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Channel, Decision, MaintenanceRequest, Prediction, RiskCase, User
from app.models.enums import MaintenanceRequestStatus, RiskCaseStatus, UserRole
from app.schemas.schemas import AuditLogOut, MaintenanceRequestOut, TransitionIn

router = APIRouter(
    prefix="/maintenance-requests", tags=["maintenance"], dependencies=[Depends(get_current_user)]
)

# Порядок стадий воркфлоу для сортировки по статусу — не алфавитный (иначе "cancelled" был
# бы раньше "draft"), а по ходу выполнения: draft -> approved -> in_progress -> completed,
# затем два терминальных прерывания.
_STATUS_ORDER = case(
    (MaintenanceRequest.status == MaintenanceRequestStatus.draft, 0),
    (MaintenanceRequest.status == MaintenanceRequestStatus.approved, 1),
    (MaintenanceRequest.status == MaintenanceRequestStatus.in_progress, 2),
    (MaintenanceRequest.status == MaintenanceRequestStatus.completed, 3),
    (MaintenanceRequest.status == MaintenanceRequestStatus.rejected, 4),
    (MaintenanceRequest.status == MaintenanceRequestStatus.cancelled, 5),
)
# Приоритет — строка без гарантированного порядка (high/medium/NULL) — явно по серьёзности.
_PRIORITY_ORDER = case((MaintenanceRequest.priority == "high", 2), (MaintenanceRequest.priority == "medium", 1), else_=0)

_SORT_COLUMNS = {"created_at": MaintenanceRequest.created_at, "status": _STATUS_ORDER, "priority": _PRIORITY_ORDER}

# Раздел 10 плана: draft -> approved -> in_progress -> completed; + rejected, cancelled.
ALLOWED_TRANSITIONS: dict[MaintenanceRequestStatus, set[MaintenanceRequestStatus]] = {
    MaintenanceRequestStatus.draft: {MaintenanceRequestStatus.approved, MaintenanceRequestStatus.rejected},
    MaintenanceRequestStatus.approved: {
        MaintenanceRequestStatus.in_progress,
        MaintenanceRequestStatus.cancelled,
    },
    MaintenanceRequestStatus.in_progress: {
        MaintenanceRequestStatus.completed,
        MaintenanceRequestStatus.cancelled,
    },
    MaintenanceRequestStatus.completed: set(),
    MaintenanceRequestStatus.rejected: set(),
    MaintenanceRequestStatus.cancelled: set(),
}


def _build_out(
    mr: MaintenanceRequest,
    approver_username: str | None,
    latest_prediction: Prediction | None = None,
    latest_decision: Decision | None = None,
    decision_username: str | None = None,
) -> MaintenanceRequestOut:
    rc = mr.risk_case
    channel = rc.channel if rc is not None else None
    obj = channel.object if channel is not None else None
    anomaly = (latest_prediction.explanation or {}).get("anomaly") if latest_prediction else None
    return MaintenanceRequestOut(
        id=mr.id,
        risk_case_id=mr.risk_case_id,
        work_type=mr.work_type,
        justification=mr.justification,
        priority=mr.priority,
        recommended_by=mr.recommended_by,
        status=mr.status,
        approved_by_user_id=mr.approved_by_user_id,
        approved_by_username=approver_username,
        approved_at=mr.approved_at,
        created_at=mr.created_at,
        category=rc.category if rc is not None else None,
        channel_label=channel.label if channel is not None else None,
        object_name=obj.name if obj is not None else None,
        ai_summary=latest_prediction.llm_summary if latest_prediction else None,
        anomaly_is_outlier=anomaly.get("is_outlier") if anomaly else None,
        dispatcher_username=decision_username,
        dispatcher_action=latest_decision.action if latest_decision else None,
        dispatcher_reason=latest_decision.reason if latest_decision else None,
    )


@router.get(
    "",
    response_model=list[MaintenanceRequestOut],
    summary="Получить список заявок",
    description=(
        "Фильтры по status и risk_case_id. Возвращает заявки с контекстом объекта, канала и риска, "
        "резюме ИИ и сигналом аномалии по последнему прогнозу риск-кейса, последним решением "
        "диспетчера. sort_by: created_at, status (по ходу выполнения, не по алфавиту) или "
        "priority (high/medium/без приоритета); sort_dir: asc или desc, по умолчанию новые/"
        "поздние стадии/высокий приоритет первыми. Учитывает доступ к объектам."
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
def list_maintenance_requests(
    response: Response,
    status_filter: MaintenanceRequestStatus | None = Query(None, alias="status"),
    risk_case_id: int | None = None,
    sort_by: Literal["created_at", "status", "priority"] = "created_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MaintenanceRequestOut]:
    """Раздел «Заявки» — обогащён контекстом риск-кейса (канал/объект/направление), резюме
    ИИ и сигналом аномалии по последнему прогнозу, и последним решением диспетчера, чтобы по
    одной строке было понятно, о чём заявка и почему она возникла, без перехода в раздел
    «Риски». `risk_case_id` — сквозная ссылка из карточки риска («Смотреть заявку»/бейдж
    существующей заявки)."""
    stmt = select(MaintenanceRequest).options(
        joinedload(MaintenanceRequest.risk_case)
        .joinedload(RiskCase.channel)
        .joinedload(Channel.object),
        joinedload(MaintenanceRequest.risk_case)
        .joinedload(RiskCase.channel)
        .joinedload(Channel.device),
    )
    if status_filter:
        stmt = stmt.where(MaintenanceRequest.status == status_filter)
    if risk_case_id is not None:
        stmt = stmt.where(MaintenanceRequest.risk_case_id == risk_case_id)
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = (
            stmt.join(RiskCase, RiskCase.id == MaintenanceRequest.risk_case_id)
            .join(Channel, Channel.id == RiskCase.channel_id)
            .where(Channel.object_id.in_(accessible))
        )
    count_stmt = select(func.count()).select_from(MaintenanceRequest)
    if status_filter:
        count_stmt = count_stmt.where(MaintenanceRequest.status == status_filter)
    if risk_case_id is not None:
        count_stmt = count_stmt.where(MaintenanceRequest.risk_case_id == risk_case_id)
    if accessible is not None:
        count_stmt = (
            count_stmt.join(RiskCase, RiskCase.id == MaintenanceRequest.risk_case_id)
            .join(Channel, Channel.id == RiskCase.channel_id)
            .where(Channel.object_id.in_(accessible))
        )
    response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

    order_col = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())
    rows = list(db.scalars(stmt.offset(offset).limit(limit)))

    approver_ids = {r.approved_by_user_id for r in rows if r.approved_by_user_id}
    approvers = (
        dict(db.execute(select(User.id, User.username).where(User.id.in_(approver_ids))).all())
        if approver_ids
        else {}
    )

    risk_case_ids = {r.risk_case_id for r in rows}
    latest_predictions = _latest_predictions_by_risk_case(db, risk_case_ids)
    latest_decisions, decision_usernames = _latest_decisions_by_risk_case(db, risk_case_ids)

    return [
        _build_out(
            r,
            approvers.get(r.approved_by_user_id),
            latest_prediction=latest_predictions.get(r.risk_case_id),
            latest_decision=latest_decisions.get(r.risk_case_id),
            decision_username=decision_usernames.get(r.risk_case_id),
        )
        for r in rows
    ]


def _latest_predictions_by_risk_case(db: Session, risk_case_ids: set[int]) -> dict[int, Prediction]:
    """Резюме ИИ и сигнал «независимой модели» — из самого свежего прогноза риск-кейса
    (тот же источник, что карточка риска), чтобы «Заявки» не выдумывали собственную выборку."""
    if not risk_case_ids:
        return {}
    rows = db.scalars(
        select(Prediction)
        .where(Prediction.risk_case_id.in_(risk_case_ids))
        .order_by(Prediction.risk_case_id, Prediction.created_at.desc())
    ).all()
    latest: dict[int, Prediction] = {}
    for p in rows:
        if p.risk_case_id not in latest:
            latest[p.risk_case_id] = p
    return latest


def _latest_decisions_by_risk_case(
    db: Session, risk_case_ids: set[int]
) -> tuple[dict[int, Decision], dict[int, str]]:
    """Последнее «Решение диспетчера» по риск-кейсу — то же, что диспетчер писал в риске,
    показывается под обоснованием заявки без перехода в «Риски»."""
    if not risk_case_ids:
        return {}, {}
    rows = db.execute(
        select(Decision, User.username)
        .join(User, User.id == Decision.user_id)
        .where(Decision.risk_case_id.in_(risk_case_ids))
        .order_by(Decision.risk_case_id, Decision.created_at.desc())
    ).all()
    latest: dict[int, Decision] = {}
    usernames: dict[int, str] = {}
    for decision, username in rows:
        if decision.risk_case_id not in latest:
            latest[decision.risk_case_id] = decision
            usernames[decision.risk_case_id] = username
    return latest, usernames


def _transition(
    request_id: int,
    to_status: MaintenanceRequestStatus,
    reason: str | None,
    db: Session,
    user: User,
) -> MaintenanceRequestOut:
    mr = db.get(MaintenanceRequest, request_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    check_object_access(mr.risk_case.channel.object_id, user, db)
    allowed = ALLOWED_TRANSITIONS.get(mr.status, set())
    if to_status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Переход {mr.status.value} -> {to_status.value} не разрешён"
        )
    old_status = mr.status
    mr.status = to_status
    if to_status == MaintenanceRequestStatus.approved:
        mr.approved_by_user_id = user.id
        mr.approved_at = dt.datetime.now(dt.timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role.value,
            entity_type="maintenance_request",
            entity_id=mr.id,
            old_state={"status": old_status.value},
            new_state={"status": to_status.value},
            reason=reason,
        )
    )

    # Подтверждённый ремонт закрывает риск-кейс — раньше «Выполнена» на заявке никак не
    # отражалась на риске: он мог висеть «Направлено» до 48ч автозакрытия воркером, даже
    # когда работа по нему уже реально сделана (см. RiskCard.tsx: диспетчеру было
    # непонятно, как перевести риск в «Решён» после ремонта). rejected/уже resolved не
    # трогаем — там статус либо не должен, либо уже не нужно менять.
    rc = mr.risk_case
    if to_status == MaintenanceRequestStatus.completed and rc is not None and rc.status not in (
        RiskCaseStatus.resolved,
        RiskCaseStatus.rejected,
    ):
        rc_old_status = rc.status
        rc.status = RiskCaseStatus.resolved
        rc.closed_at = dt.datetime.now(dt.timezone.utc)
        db.add(
            AuditLog(
                user_id=user.id,
                role=user.role.value,
                entity_type="risk_case",
                entity_id=rc.id,
                old_state={"status": rc_old_status.value},
                new_state={"status": rc.status.value},
                reason="Заявка на обслуживание выполнена",
            )
        )

    db.commit()
    db.refresh(mr)
    approver = db.get(User, mr.approved_by_user_id) if mr.approved_by_user_id else None
    latest_predictions = _latest_predictions_by_risk_case(db, {mr.risk_case_id})
    latest_decisions, decision_usernames = _latest_decisions_by_risk_case(db, {mr.risk_case_id})
    return _build_out(
        mr,
        approver.username if approver else None,
        latest_prediction=latest_predictions.get(mr.risk_case_id),
        latest_decision=latest_decisions.get(mr.risk_case_id),
        decision_username=decision_usernames.get(mr.risk_case_id),
    )


@router.get(
    "/{request_id}/history",
    response_model=list[AuditLogOut],
    summary="История изменений заявки",
    description=(
        "Полная история переходов статуса заявки (кто, когда, из какого состояния в какое, с каким "
        "комментарием) — записи AuditLog по этой заявке, новые первыми. Доступно диспетчеру, аналитику "
        "и администратору с доступом к объекту заявки."
    ),
    responses={
        403: {"description": "Недостаточно прав или нет доступа к объекту"},
        404: {"description": "Заявка не найдена"},
        401: {"description": "Требуется вход или токен недействителен"},
    },
)
def get_request_history(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.analyst, UserRole.admin)),
) -> list[AuditLogOut]:
    mr = db.get(MaintenanceRequest, request_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    check_object_access(mr.risk_case.channel.object_id, user, db)

    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "maintenance_request", AuditLog.entity_id == request_id)
            .order_by(AuditLog.created_at.desc())
        )
    )
    usernames = dict(
        db.execute(select(User.id, User.username).where(User.id.in_({r.user_id for r in rows if r.user_id}))).all()
    )
    return [
        AuditLogOut(
            id=r.id,
            user_id=r.user_id,
            username=usernames.get(r.user_id),
            role=r.role,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            old_state=r.old_state,
            new_state=r.new_state,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/{request_id}/approve",
    response_model=MaintenanceRequestOut,
    summary="Утвердить заявку",
    description=(
        "Доступно диспетчеру и администратору. Переводит заявку из draft в approved и записывает "
        "автора и время утверждения."
    ),
    responses={
        403: {
            "description": "Недостаточно прав или нет доступа к объекту",
        },
        404: {
            "description": "Заявка не найдена",
        },
        409: {
            "description": "Утверждение невозможно из текущего статуса",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def approve(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequestOut:
    return _transition(request_id, MaintenanceRequestStatus.approved, None, db, user)


@router.post(
    "/{request_id}/transitions",
    response_model=MaintenanceRequestOut,
    summary="Изменить статус заявки",
    description=(
        "Доступно диспетчеру и администратору. Переходы: draft → approved или rejected; approved → "
        "in_progress или cancelled; in_progress → completed или cancelled. Из completed, rejected и "
        "cancelled переходов нет. Переход в completed также закрывает связанный риск-кейс "
        "(status resolved, closed_at = сейчас), если он ещё не resolved/rejected."
    ),
    responses={
        403: {
            "description": "Недостаточно прав или нет доступа к объекту",
        },
        404: {
            "description": "Заявка не найдена",
        },
        409: {
            "description": "Переход из текущего статуса не разрешён",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def transition(
    request_id: int,
    payload: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequestOut:
    return _transition(request_id, payload.to_status, payload.reason, db, user)
