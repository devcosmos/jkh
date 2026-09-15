from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, verify_password
from app.models.entities import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == form.username))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Учётная запись отключена")
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return {"access_token": token, "token_type": "bearer", "role": user.role.value}
