"""Решения диспетчера по риск-кейсу (POST /risk-cases/{id}/decisions) — переходы статуса
и права доступа (только dispatcher/analyst/admin, docs/documentation/Устройство_системы.md, раздел «Сценарий диспетчера»)."""
import datetime as dt

from app.models.entities import Channel, RiskCase
from app.models.enums import RiskCaseStatus, UserRole


def _make_risk_case(db_session) -> RiskCase:
    channel = Channel(external_channel_id=42, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=dt.datetime.now(dt.timezone.utc))
    db_session.add(rc)
    db_session.commit()
    db_session.refresh(rc)
    return rc


def test_dispatch_action_sets_status(client, db_session, auth_headers):
    rc = _make_risk_case(db_session)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"}, headers=headers)
    assert r.status_code == 200
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.dispatched
    assert rc.closed_at is None


def test_reject_action_closes_case(client, db_session, auth_headers):
    rc = _make_risk_case(db_session)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(
        f"/api/risk-cases/{rc.id}/decisions",
        json={"action": "reject", "reason": "ложное срабатывание"},
        headers=headers,
    )
    assert r.status_code == 200
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.rejected
    assert rc.closed_at is not None


def test_observe_action_sets_status(client, db_session, auth_headers):
    rc = _make_risk_case(db_session)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "observe"}, headers=headers)
    assert r.status_code == 200
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.observing


def test_decision_requires_role(client, db_session, auth_headers):
    """UserRole не содержит роли без прав по умолчанию в схеме, поэтому проверяем, что
    хотя бы отсутствие токена блокирует доступ (полная матрица ролей — в deps.require_role)."""
    rc = _make_risk_case(db_session)
    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"})
    assert r.status_code == 401


def test_decision_on_missing_risk_case_404(client, db_session, auth_headers):
    headers = auth_headers(UserRole.dispatcher)
    r = client.post("/api/risk-cases/999999/decisions", json={"action": "dispatch"}, headers=headers)
    assert r.status_code == 404
