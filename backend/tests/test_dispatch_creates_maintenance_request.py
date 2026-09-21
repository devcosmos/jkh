"""Решение диспетчера «направить на проверку» должно быть видно в разделе «Заявки» — до
этой правки Decision(action=dispatch) и MaintenanceRequest были не связаны: диспетчер мог
направить риск на проверку, а раздел «Заявки» оставался пустым, если раньше не сработало
авто-правило worker'а по порогу вероятности (см. docs/Статус.md, app.services.maintenance_requests)."""
import datetime as dt

from app.models.entities import Channel, MaintenanceRequest, Object, RiskCase
from app.models.enums import MaintenanceRequestStatus, RiskCaseStatus, UserRole

NOW = dt.datetime.now(dt.timezone.utc)


def _make_case(db_session, sensor_type="Состояние насоса") -> RiskCase:
    obj = Object(name="Объект для диспетчинга")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=6001, sensor_type=sensor_type, object_id=obj.id, display_name="Насос №1")
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(
        channel_id=channel.id, status=RiskCaseStatus.new, priority="medium",
        category="sensor_failure_pump_fan", opened_at=NOW,
    )
    db_session.add(rc)
    db_session.commit()
    db_session.refresh(rc)
    return rc


def test_dispatch_creates_maintenance_request(client, db_session, auth_headers):
    rc = _make_case(db_session)
    headers = auth_headers(UserRole.dispatcher)

    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"}, headers=headers)
    assert r.status_code == 200

    requests = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).all()
    assert len(requests) == 1
    assert requests[0].status == MaintenanceRequestStatus.draft
    assert "решению диспетчера" in requests[0].justification


def test_dispatch_is_idempotent_with_existing_active_request(client, db_session, auth_headers):
    """Если для риск-кейса уже есть незакрытая заявка (например, авто-созданная worker'ом
    заранее), повторное «направить на проверку» не должно плодить вторую."""
    rc = _make_case(db_session)
    existing = MaintenanceRequest(
        risk_case_id=rc.id,
        work_type="Диагностика и техническое обслуживание насоса",
        status=MaintenanceRequestStatus.draft,
    )
    db_session.add(existing)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"}, headers=headers)
    assert r.status_code == 200

    requests = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).all()
    assert len(requests) == 1


def test_dispatch_without_work_type_template_does_not_crash(client, db_session, auth_headers):
    """Тип датчика без шаблона рекомендации (WORK_TYPE_BY_SENSOR_TYPE) — решение сохраняется,
    заявка просто не создаётся, без ошибки."""
    rc = _make_case(db_session, sensor_type="Неизвестный тип")
    headers = auth_headers(UserRole.dispatcher)

    r = client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"}, headers=headers)
    assert r.status_code == 200
    assert db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).count() == 0


def test_requests_list_is_enriched_and_filterable_by_risk_case(client, db_session, auth_headers):
    rc = _make_case(db_session)
    headers = auth_headers(UserRole.dispatcher)
    client.post(f"/api/risk-cases/{rc.id}/decisions", json={"action": "dispatch"}, headers=headers)

    r = client.get(f"/api/maintenance-requests?risk_case_id={rc.id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    item = body[0]
    assert item["risk_case_id"] == rc.id
    assert item["category"] == "sensor_failure_pump_fan"
    assert item["channel_label"] == "Насос №1"
    assert item["object_name"] == "Объект для диспетчинга"
    assert "created_at" in item


def test_requests_list_shows_dispatcher_decision(client, db_session, auth_headers):
    """Решение диспетчера («Направить на проверку» + причина) должно быть видно под
    обоснованием заявки, без перехода в «Риски» — раздел TODO 1."""
    rc = _make_case(db_session)
    headers = auth_headers(UserRole.dispatcher)
    client.post(
        f"/api/risk-cases/{rc.id}/decisions",
        json={"action": "dispatch", "reason": "Похоже на реальный риск — требует проверки"},
        headers=headers,
    )

    r = client.get(f"/api/maintenance-requests?risk_case_id={rc.id}", headers=headers)
    assert r.status_code == 200
    item = r.json()[0]
    assert item["dispatcher_action"] == "dispatch"
    assert item["dispatcher_reason"] == "Похоже на реальный риск — требует проверки"
    assert item["dispatcher_username"]
