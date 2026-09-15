"""Смена собственного пароля (POST /api/auth/change-password) — раньше пароль менялся
только вручную в БД. Требует знания текущего пароля, не только валидного токена."""
from app.core.security import hash_password
from app.models.entities import User
from app.models.enums import UserRole


def _seed_user(db_session, username="ivanov", password="old-pass-123", role=UserRole.dispatcher) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, username, password):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_change_password_success_allows_login_with_new_password(client, db_session):
    _seed_user(db_session, username="ivanov", password="old-pass-123")
    headers = _login(client, "ivanov", "old-pass-123")

    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "old-pass-123", "new_password": "new-pass-456"},
        headers=headers,
    )
    assert r.status_code == 204

    r = client.post("/api/auth/login", data={"username": "ivanov", "password": "new-pass-456"})
    assert r.status_code == 200
    r = client.post("/api/auth/login", data={"username": "ivanov", "password": "old-pass-123"})
    assert r.status_code == 401


def test_change_password_rejects_wrong_current_password(client, db_session):
    _seed_user(db_session, username="petrov", password="old-pass-123")
    headers = _login(client, "petrov", "old-pass-123")

    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "totally-wrong", "new_password": "new-pass-456"},
        headers=headers,
    )
    assert r.status_code == 401

    r = client.post("/api/auth/login", data={"username": "petrov", "password": "old-pass-123"})
    assert r.status_code == 200


def test_change_password_requires_authentication(client, db_session):
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "whatever", "new_password": "new-pass-456"},
    )
    assert r.status_code == 401


def test_change_password_rejects_too_short_new_password(client, db_session):
    _seed_user(db_session, username="sidorov", password="old-pass-123")
    headers = _login(client, "sidorov", "old-pass-123")

    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "old-pass-123", "new_password": "short"},
        headers=headers,
    )
    assert r.status_code == 422


def test_change_password_only_affects_own_account(client, db_session):
    user_a = _seed_user(db_session, username="a-user", password="a-pass-123")
    _seed_user(db_session, username="b-user", password="b-pass-123")
    headers = _login(client, "a-user", "a-pass-123")

    client.post(
        "/api/auth/change-password",
        json={"current_password": "a-pass-123", "new_password": "a-new-pass-456"},
        headers=headers,
    )

    db_session.refresh(user_a)
    r = client.post("/api/auth/login", data={"username": "b-user", "password": "b-pass-123"})
    assert r.status_code == 200
