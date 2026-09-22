"""Локальная JWT-аутентификация (docs/documentation/Устройство_системы.md — LDAP/AD отложены для MVP)."""
from app.core.security import hash_password
from app.models.entities import User
from app.models.enums import UserRole


def _seed_user(db_session, username="ivanov", password="s3cret-pass", role=UserRole.dispatcher, is_active=True):
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=is_active)
    db_session.add(user)
    db_session.commit()
    return user


def test_login_success_returns_token(client, db_session):
    _seed_user(db_session, username="ivanov", password="s3cret-pass")
    r = client.post("/api/auth/login", data={"username": "ivanov", "password": "s3cret-pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_rejected(client, db_session):
    _seed_user(db_session, username="ivanov", password="s3cret-pass")
    r = client.post("/api/auth/login", data={"username": "ivanov", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_rejected(client, db_session):
    r = client.post("/api/auth/login", data={"username": "ghost", "password": "whatever"})
    assert r.status_code == 401


def test_login_inactive_user_rejected(client, db_session):
    _seed_user(db_session, username="disabled", password="s3cret-pass", is_active=False)
    r = client.post("/api/auth/login", data={"username": "disabled", "password": "s3cret-pass"})
    assert r.status_code == 401


def test_protected_endpoint_rejects_missing_token(client, db_session):
    r = client.get("/api/risk-cases")
    assert r.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client, db_session):
    r = client.get("/api/risk-cases", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_protected_endpoint_accepts_valid_token(client, db_session, auth_headers):
    headers = auth_headers(UserRole.analyst)
    r = client.get("/api/risk-cases", headers=headers)
    assert r.status_code == 200
