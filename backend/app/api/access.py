from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.db import get_db
from app.core.security import hash_password
from app.models.entities import AuditLog, Object, User, UserObjectAccess
from app.models.enums import UserRole
from app.schemas.schemas import ObjectAccessIn, UserCreateIn, UserOut

router = APIRouter(prefix="/access", tags=["access"], dependencies=[Depends(require_role(UserRole.admin))])


@router.get(
    "/users",
    response_model=list[UserOut],
    summary="Получить пользователей и их доступ",
    description="Только администратор. Возвращает роли и назначенные object_ids.",
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
        },
    },
)
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    """Пользователи + назначенные объекты — раздел «Пользователи и доступ» админ-панели.
    Только администратор (см. зависимость роутера)."""
    users = list(db.scalars(select(User).order_by(User.id)))
    access_rows = db.execute(select(UserObjectAccess.user_id, UserObjectAccess.object_id)).all()
    by_user: dict[int, list[int]] = {}
    for uid, oid in access_rows:
        by_user.setdefault(uid, []).append(oid)
    return [
        UserOut(
            id=u.id,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
            object_ids=by_user.get(u.id, []),
        )
        for u in users
    ]


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя",
    description="Только администратор. Логин — от 3 до 64 символов, пароль — не короче 8 символов.",
    responses={
        409: {
            "description": "Логин уже занят",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
        },
    },
)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
) -> UserOut:
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой логин уже занят")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            user_id=admin.id,
            role=admin.role.value,
            entity_type="user",
            entity_id=user.id,
            old_state=None,
            new_state={"username": user.username, "role": user.role.value},
            reason="Создание пользователя администратором",
        )
    )
    db.commit()
    db.refresh(user)
    return UserOut(id=user.id, username=user.username, role=user.role, is_active=user.is_active, object_ids=[])


@router.get(
    "/users/{user_id}/objects",
    response_model=list[int],
    summary="Получить назначенные пользователю объекты",
    description="Только администратор. Пустой список назначений означает отсутствие ограничения по объектам.",
    responses={
        404: {
            "description": "Пользователь не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
        },
    },
)
def list_user_object_access(user_id: int, db: Session = Depends(get_db)) -> list[int]:
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    return list(
        db.scalars(select(UserObjectAccess.object_id).where(UserObjectAccess.user_id == user_id))
    )


@router.post(
    "/users/{user_id}/objects",
    status_code=status.HTTP_201_CREATED,
    summary="Назначить доступ к объекту",
    description="Только администратор. Повторное назначение не создаёт дубликат.",
    responses={
        404: {
            "description": "Пользователь или объект не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
        },
    },
)
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


@router.delete(
    "/users/{user_id}/objects/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отозвать назначение объекта",
    description=(
        "Только администратор. Повторный отзыв возвращает 204. После удаления последнего назначения "
        "ограничение по объектам перестаёт действовать."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        403: {
            "description": "Доступно только администратору",
        },
    },
)
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
