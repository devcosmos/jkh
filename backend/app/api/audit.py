from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.db import get_db
from app.models.entities import AuditLog, User
from app.models.enums import UserRole
from app.schemas.schemas import AuditLogOut

router = APIRouter(prefix="/audit-log", tags=["audit"], dependencies=[Depends(require_role(UserRole.admin))])


@router.get(
    "",
    response_model=list[AuditLogOut],
    summary="Получить журнал аудита",
    description=(
        "Только администратор. Фильтр по entity_type; новые записи идут первыми. Содержит автора, "
        "время и изменения состояния."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
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
def list_audit_log(
    entity_type: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    """Полная история решений/переходов/назначений доступа — раздел 11 плана
    (трассируемость). Доступ только администратору: записи могут содержать причины решений
    по чужим объектам вне матрицы доступа текущего пользователя."""
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = list(db.scalars(stmt))

    usernames = dict(
        db.execute(
            select(User.id, User.username).where(User.id.in_({r.user_id for r in rows if r.user_id}))
        ).all()
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
