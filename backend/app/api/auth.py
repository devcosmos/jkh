from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import User
from app.schemas.schemas import ChangePasswordIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Получить токен доступа",
    description=(
        "Принимает логин и пароль в формате application/x-www-form-urlencoded. Возвращает "
        "access_token, token_type (bearer) и role. Токен используется в заголовке Authorization: "
        "Bearer <access_token>."
    ),
    responses={
        401: {
            "description": "Неверные учётные данные или учётная запись отключена",
        },
    },
)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == form.username))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Учётная запись отключена")
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return {"access_token": token, "token_type": "bearer", "role": user.role.value}


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сменить свой пароль",
    description="Требует токен доступа и текущий пароль. Новый пароль — не короче 8 символов.",
    responses={
        401: {
            "description": "Неверный текущий пароль или недействительный токен",
        },
    },
)
def change_password(
    payload: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Смена собственного пароля — раздел «Открытые вопросы» сводки: пароль администратора
    сейчас менялся только вручную в БД. Требует текущий пароль (не только роль/токен), чтобы
    перехваченный токен не давал захватить учётку сменой пароля без знания старого."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный текущий пароль")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
