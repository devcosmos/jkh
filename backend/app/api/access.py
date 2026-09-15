from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Object, User, UserObjectAccess
from app.models.enums import UserRole
from app.schemas.schemas import ObjectAccessIn

router = APIRouter(prefix="/access", tags=["access"], dependencies=[Depends(require_role(UserRole.admin))])


@router.get("/users/{user_id}/objects", response_model=list[int])
def list_user_object_access(user_id: int, db: Session = Depends(get_db)) -> list[int]:
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    return list(
        db.scalars(select(UserObjectAccess.object_id).where(UserObjectAccess.user_id == user_id))
    )


@router.post("/users/{user_id}/objects", status_code=status.HTTP_201_CREATED)
def grant_object_access(
    user_id: int,
    payload: ObjectAccessIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
) -> None:
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    if db.get(Object, payload.object_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Объект не найден")

    db.add(UserObjectAccess(user_id=user_id, object_id=payload.object_id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return  # уже назначено — идемпотентно, не ошибка
    db.add(
        AuditLog(
            user_id=admin.id,
            role=admin.role.value,
            entity_type="user_object_access",
            entity_id=user_id,
            old_state=None,
            new_state={"granted_object_id": payload.object_id},
            reason=f"Назначение доступа к объекту {payload.object_id}",
        )
    )
    db.commit()


@router.delete("/users/{user_id}/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_object_access(
    user_id: int,
    object_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
) -> None:
    row = db.scalar(
        select(UserObjectAccess).where(
            UserObjectAccess.user_id == user_id, UserObjectAccess.object_id == object_id
        )
    )
    if row is None:
        return  # уже нет доступа — идемпотентно
    db.delete(row)
    db.add(
        AuditLog(
            user_id=admin.id,
            role=admin.role.value,
            entity_type="user_object_access",
            entity_id=user_id,
            old_state={"revoked_object_id": object_id},
            new_state=None,
            reason=f"Отзыв доступа к объекту {object_id}",
        )
    )
    db.commit()
