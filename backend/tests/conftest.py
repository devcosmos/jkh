"""Фикстуры для тестов backend. Требует реальный Postgres (используются enum/JSON-типы,
не совместимые со SQLite) — см. backend/README.md, раздел «Тесты», для инструкции запуска.
"""
import os

os.environ.setdefault(
    "JKH_DATABASE_URL", "postgresql+psycopg://jkh:jkh@localhost:55432/jkh_test"
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.entities import User
from app.models.enums import UserRole

engine = create_engine(os.environ["JKH_DATABASE_URL"])
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Полная очистка данных между тестами — проще и надёжнее вложенных транзакций
    при работе с несколькими db.commit() внутри тестируемого кода (worker коммитит сам)."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))


@pytest.fixture
def db_session():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_user(db_session, username: str, role: UserRole, password: str = "test-pass-123") -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(db_session):
    """Фабрика: auth_headers(role) -> заголовок Authorization с реальным JWT (через
    create_access_token, тот же путь, что и в POST /api/auth/login)."""

    def _make(role: UserRole = UserRole.dispatcher, username: str | None = None) -> dict:
        username = username or f"{role.value}-{os.urandom(4).hex()}"
        user = make_user(db_session, username, role)
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return {"Authorization": f"Bearer {token}"}

    return _make
