"""Переходы статусов заявки (docs/documentation/Устройство_системы.md, раздел «Сценарий диспетчера»):
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


def test_completing_request_resolves_risk_case(client, db_session, auth_headers):
    mr = _make_request(db_session, status=MaintenanceRequestStatus.in_progress)
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(
        f"/api/maintenance-requests/{mr.id}/transitions",
        json={"to_status": "completed", "reason": "ремонт выполнен"},
        headers=headers,
    )
    assert r.status_code == 200
    db_session.refresh(mr)
    db_session.refresh(mr.risk_case)
    assert mr.risk_case.status == RiskCaseStatus.resolved
    assert mr.risk_case.closed_at is not None


def test_completing_request_does_not_reopen_already_rejected_risk_case(client, db_session, auth_headers):
    mr = _make_request(db_session, status=MaintenanceRequestStatus.in_progress)
    mr.risk_case.status = RiskCaseStatus.rejected
    db_session.commit()
    headers = auth_headers(UserRole.dispatcher)
    r = client.post(
        f"/api/maintenance-requests/{mr.id}/transitions",
        json={"to_status": "completed", "reason": "ремонт выполнен"},
        headers=headers,
    )
    assert r.status_code == 200
    db_session.refresh(mr.risk_case)
    assert mr.risk_case.status == RiskCaseStatus.rejected


def test_request_history_endpoint_lists_transitions_newest_first(client, db_session, auth_headers):
    mr = _make_request(db_session)
    headers = auth_headers(UserRole.dispatcher)
    client.post(f"/api/maintenance-requests/{mr.id}/approve", headers=headers)
    client.post(
        f"/api/maintenance-requests/{mr.id}/transitions",
        json={"to_status": "in_progress", "reason": "выехали на объект"},
        headers=headers,
    )

    r = client.get(f"/api/maintenance-requests/{mr.id}/history", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["new_state"] == {"status": "in_progress"}
    assert body[0]["reason"] == "выехали на объект"
    assert body[1]["new_state"] == {"status": "approved"}
    assert all(entry["username"] for entry in body)


def test_request_history_respects_object_access(client, db_session, auth_headers):
    from app.models.entities import Object, User, UserObjectAccess

    other_object = Object(name="Чужой объект")
    db_session.add(other_object)
    db_session.flush()
    channel = Channel(external_channel_id=999, sensor_type="Состояние насоса", object_id=other_object.id)
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=dt.datetime.now(dt.timezone.utc))
    db_session.add(rc)
    db_session.flush()
    mr = MaintenanceRequest(risk_case_id=rc.id, work_type="Диагностика насоса", status=MaintenanceRequestStatus.draft)
    db_session.add(mr)
    db_session.commit()
    db_session.refresh(mr)

    headers = auth_headers(UserRole.dispatcher, username="restricted-dispatcher-2")
    user = db_session.query(User).filter_by(username="restricted-dispatcher-2").one()
    other_assigned_object = Object(name="Назначенный объект")
    db_session.add(other_assigned_object)
    db_session.flush()
    db_session.add(UserObjectAccess(user_id=user.id, object_id=other_assigned_object.id))
    db_session.commit()

    r = client.get(f"/api/maintenance-requests/{mr.id}/history", headers=headers)
    assert r.status_code == 403


def test_sort_by_status_orders_by_workflow_stage_not_alphabet(client, db_session, auth_headers):
    """cancelled < draft алфавитно, но по ходу выполнения draft раньше cancelled — сортировка
    должна идти по стадии воркфлоу (draft -> approved -> in_progress -> completed -> rejected
    -> cancelled), а не по алфавиту enum-значений."""

    def _make(ext_id, status):
        channel = Channel(external_channel_id=ext_id, sensor_type="Состояние насоса")
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

    cancelled = _make(101, MaintenanceRequestStatus.cancelled)
    draft = _make(102, MaintenanceRequestStatus.draft)
    approved = _make(103, MaintenanceRequestStatus.approved)

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/maintenance-requests?sort_by=status&sort_dir=asc", headers=headers)
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids.index(draft.id) < ids.index(approved.id) < ids.index(cancelled.id)


def test_sort_by_priority_puts_high_first_by_default(client, db_session, auth_headers):
    channel = Channel(external_channel_id=2, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()

    def _make(priority):
        rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=dt.datetime.now(dt.timezone.utc))
        db_session.add(rc)
        db_session.flush()
        mr = MaintenanceRequest(risk_case_id=rc.id, work_type="Диагностика насоса", priority=priority)
        db_session.add(mr)
        db_session.commit()
        db_session.refresh(mr)
        return mr

    low = _make(None)
    medium = _make("medium")
    high = _make("high")

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/maintenance-requests?sort_by=priority", headers=headers)
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids.index(high.id) < ids.index(medium.id) < ids.index(low.id)
