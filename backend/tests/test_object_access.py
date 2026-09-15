"""Минимальная матрица доступа по объектам (раздел 12 плана — полная версия с
подразделениями отложена как требование будущего пилота). Правила:
- admin видит и меняет всё, независимо от назначений;
- пользователь без явных назначений (user_object_access пуст) не ограничен — сознательное
  упрощение MVP, чтобы не сломать демонстрацию для ещё не настроенных пользователей;
- пользователь с хотя бы одним назначением видит и меняет только эти объекты."""
import datetime as dt

from app.models.entities import Channel, MaintenanceRequest, Object, RiskCase, UserObjectAccess
from app.models.enums import RiskCaseStatus, UserRole


def _make_object_with_case(db_session, ext_channel_id: int) -> tuple[Object, Channel, RiskCase]:
    obj = Object(name=f"Объект {ext_channel_id}")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=ext_channel_id, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=dt.datetime.now(dt.timezone.utc))
    db_session.add(rc)
    db_session.commit()
    return obj, channel, rc


def test_unrestricted_user_sees_all_risk_cases(client, db_session, auth_headers):
    _make_object_with_case(db_session, 1001)
    _make_object_with_case(db_session, 1002)
    headers = auth_headers(UserRole.dispatcher)  # без назначений -> не ограничен
    r = client.get("/api/risk-cases", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_restricted_user_sees_only_assigned_object(client, db_session, auth_headers):
    obj_a, _, rc_a = _make_object_with_case(db_session, 2001)
    _, _, rc_b = _make_object_with_case(db_session, 2002)

    headers = auth_headers(UserRole.dispatcher, username="restricted-dispatcher")
    # достаём пользователя, чтобы назначить доступ
    from app.models.entities import User

    user = db_session.query(User).filter_by(username="restricted-dispatcher").one()
    db_session.add(UserObjectAccess(user_id=user.id, object_id=obj_a.id))
    db_session.commit()

    r = client.get("/api/risk-cases", headers=headers)
    assert r.status_code == 200
    ids = {rc["id"] for rc in r.json()}
    assert ids == {rc_a.id}


def test_restricted_user_gets_403_on_forbidden_risk_case(client, db_session, auth_headers):
    obj_a, _, rc_a = _make_object_with_case(db_session, 3001)
    _, _, rc_b = _make_object_with_case(db_session, 3002)

    headers = auth_headers(UserRole.dispatcher, username="restricted-2")
    from app.models.entities import User

    user = db_session.query(User).filter_by(username="restricted-2").one()
    db_session.add(UserObjectAccess(user_id=user.id, object_id=obj_a.id))
    db_session.commit()

    r = client.get(f"/api/risk-cases/{rc_a.id}", headers=headers)
    assert r.status_code == 200
    r = client.get(f"/api/risk-cases/{rc_b.id}", headers=headers)
    assert r.status_code == 403


def test_restricted_user_cannot_decide_on_forbidden_risk_case(client, db_session, auth_headers):
    _, _, rc_a = _make_object_with_case(db_session, 4001)
    _, _, rc_b = _make_object_with_case(db_session, 4002)

    headers = auth_headers(UserRole.dispatcher, username="restricted-3")
    from app.models.entities import User

    user = db_session.query(User).filter_by(username="restricted-3").one()
    obj_a = db_session.get(RiskCase, rc_a.id).channel.object_id
    db_session.add(UserObjectAccess(user_id=user.id, object_id=obj_a))
    db_session.commit()

    r = client.post(f"/api/risk-cases/{rc_b.id}/decisions", json={"action": "observe"}, headers=headers)
    assert r.status_code == 403


def test_admin_bypasses_restriction_even_with_no_assignment(client, db_session, auth_headers):
    _make_object_with_case(db_session, 5001)
    _make_object_with_case(db_session, 5002)
    headers = auth_headers(UserRole.admin)
    r = client.get("/api/risk-cases", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_admin_can_grant_and_revoke_access(client, db_session, auth_headers):
    from tests.conftest import make_user

    obj = Object(name="Объект для гранта")
    db_session.add(obj)
    db_session.commit()

    admin_headers = auth_headers(UserRole.admin)
    target_user = make_user(db_session, "grantee", UserRole.dispatcher)

    r = client.post(
        f"/api/access/users/{target_user.id}/objects",
        json={"object_id": obj.id},
        headers=admin_headers,
    )
    assert r.status_code == 201

    r = client.get(f"/api/access/users/{target_user.id}/objects", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == [obj.id]

    r = client.delete(
        f"/api/access/users/{target_user.id}/objects/{obj.id}", headers=admin_headers
    )
    assert r.status_code == 204

    r = client.get(f"/api/access/users/{target_user.id}/objects", headers=admin_headers)
    assert r.json() == []


def test_grant_endpoint_requires_admin_role(client, db_session, auth_headers):
    headers = auth_headers(UserRole.dispatcher)
    r = client.post("/api/access/users/1/objects", json={"object_id": 1}, headers=headers)
    assert r.status_code == 403
