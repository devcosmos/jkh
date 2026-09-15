"""Переходы статусов заявки (docs/План_реализации.md, раздел 10):
draft -> approved -> in_progress -> completed; + rejected, cancelled. Терминальные статусы
не допускают дальнейших переходов. Права: approve/transitions только dispatcher/admin."""
import datetime as dt

import pytest

from app.models.entities import Channel, MaintenanceRequest, RiskCase
from app.models.enums import MaintenanceRequestStatus, RiskCaseStatus, UserRole


def _make_request(db_session, status=MaintenanceRequestStatus.draft) -> MaintenanceRequest:
    channel = Channel(external_channel_id=1, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=dt.datetime.now(dt.timezone.utc))
    db_session.add(rc)
    db_session.flush()
    mr = MaintenanceRequest(risk_case_id=rc.id, work_type="Диагностика насоса", status=status)
    db_session.add(mr)
    db_session.commit()
    db_session.refresh(mr)
    return mr


def test_draft_to_approved_via_approve_endpoint(client, db_session, auth_headers):
    mr = _make_request(db_session)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(f"/api/maintenance-requests/{mr.id}/approve", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["approved_by_user_id"] is not None


def test_approve_requires_dispatcher_or_admin_role(client, db_session, auth_headers):
    mr = _make_request(db_session)
    headers = auth_headers(UserRole.analyst)
    r = client.post(f"/api/maintenance-requests/{mr.id}/approve", headers=headers)
    assert r.status_code == 403


def test_approve_rejects_unauthenticated(client, db_session):
    mr = _make_request(db_session)
    r = client.post(f"/api/maintenance-requests/{mr.id}/approve")
    assert r.status_code == 401


@pytest.mark.parametrize(
    "from_status,to_status,expected_code",
    [
        (MaintenanceRequestStatus.draft, MaintenanceRequestStatus.in_progress, 409),  # нельзя перепрыгнуть approved
        (MaintenanceRequestStatus.approved, MaintenanceRequestStatus.in_progress, 200),
        (MaintenanceRequestStatus.in_progress, MaintenanceRequestStatus.completed, 200),
        (MaintenanceRequestStatus.completed, MaintenanceRequestStatus.in_progress, 409),  # терминальный статус
        (MaintenanceRequestStatus.rejected, MaintenanceRequestStatus.approved, 409),  # терминальный статус
    ],
)
def test_transition_rules(client, db_session, auth_headers, from_status, to_status, expected_code):
    mr = _make_request(db_session, status=from_status)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(
        f"/api/maintenance-requests/{mr.id}/transitions",
        json={"to_status": to_status.value, "reason": "test"},
        headers=headers,
    )
    assert r.status_code == expected_code


def test_transition_writes_audit_log(client, db_session, auth_headers):
    from app.models.entities import AuditLog

    mr = _make_request(db_session, status=MaintenanceRequestStatus.approved)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(
        f"/api/maintenance-requests/{mr.id}/transitions",
        json={"to_status": "cancelled", "reason": "передумали"},
        headers=headers,
    )
    assert r.status_code == 200
    log = (
        db_session.query(AuditLog)
        .filter_by(entity_type="maintenance_request", entity_id=mr.id)
        .one()
    )
    assert log.old_state == {"status": "approved"}
    assert log.new_state == {"status": "cancelled"}
    assert log.reason == "передумали"
