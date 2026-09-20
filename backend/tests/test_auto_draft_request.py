"""Автосоздание черновика заявки при открытии риск-кейса (docs/План_реализации.md, раздел
10; app.workers.replay_worker.maybe_create_draft_request). Условие создания: риск превышает
порог, есть шаблон для типа датчика, для риск-кейса ещё нет незакрытой заявки того же вида
работ. Повторный вызов на одном риск-кейсе не создаёт вторую заявку (дедуп по устройству +
виду работ + активному случаю, а не по ID прогноза)."""
import datetime as dt

from app.core.config import settings
from app.models.entities import AuditLog, Channel, Device, MaintenanceRequest, RiskCase
from app.models.enums import MaintenanceRequestStatus, RiskCaseStatus
from app.workers.replay_worker import TRACKS, maybe_create_draft_request

PUMP_FAN_TRACK = TRACKS[0]  # насос/вентилятор — совпадает с sensor_type, используемым в этих тестах

FEATURES = {
    "current_state": "Неисправен",
    "n_events_7d": 12,
    "n_transitions_24h": 3,
    "seconds_since_last_event": 90.0,
}
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _make_channel_and_case(db_session, sensor_type: str, priority: str = "high") -> tuple[Channel, RiskCase]:
    channel = Channel(external_channel_id=7001, sensor_type=sensor_type)
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, priority=priority, opened_at=NOW)
    db_session.add(rc)
    db_session.flush()
    return channel, rc


def test_creates_draft_with_expected_fields(db_session):
    channel, rc = _make_channel_and_case(db_session, "Состояние насоса")
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.commit()

    requests = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).all()
    assert len(requests) == 1
    mr = requests[0]
    assert mr.status == MaintenanceRequestStatus.draft
    assert mr.work_type == "Диагностика и техническое обслуживание насоса"
    assert mr.priority == "high"
    assert mr.recommended_by is None
    assert "риск-кейсу #" in mr.justification
    assert "0.90" in mr.justification
    assert "не сопоставлено" in mr.justification  # у канала нет привязанного устройства


def test_justification_includes_device_label_when_linked(db_session):
    """scripts/link_channels_to_devices.py: устройство определяется эвристикой по имени
    канала (раздел 10 плана: «состав черновика: устройство и объект»)."""
    channel, rc = _make_channel_and_case(db_session, "Состояние вентилятора")
    device = Device(external_id="В8-ПК96", device_type="вентилятор")
    db_session.add(device)
    db_session.flush()
    channel.device_id = device.id
    db_session.flush()

    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.commit()

    mr = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).one()
    assert "В8-ПК96" in mr.justification


def test_writes_audit_log_on_creation(db_session):
    channel, rc = _make_channel_and_case(db_session, "Состояние насоса")
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.commit()

    mr = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).one()
    log = db_session.query(AuditLog).filter_by(entity_type="maintenance_request", entity_id=mr.id).one()
    assert log.new_state["status"] == "draft"
    assert log.new_state["source"] == "auto_worker"
    assert log.old_state is None


def test_below_threshold_creates_nothing(db_session):
    channel, rc = _make_channel_and_case(db_session, "Состояние насоса")
    proba_below = settings.auto_draft_risk_threshold - 0.01
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=proba_below, tick_end=NOW)
    db_session.commit()

    assert db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).count() == 0


def test_no_template_for_unknown_sensor_type_creates_nothing(db_session):
    channel, rc = _make_channel_and_case(db_session, "Датчик движения")
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.commit()

    assert db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).count() == 0


def test_second_call_on_same_case_does_not_duplicate(db_session):
    """Раздел 10 плана: повторный расчёт/смена модели на том же активном случае не создаёт
    вторую заявку — дедуп по (устройство, вид работы, активный риск-кейс)."""
    channel, rc = _make_channel_and_case(db_session, "Состояние насоса")
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.flush()
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.95, tick_end=NOW + dt.timedelta(hours=1))
    db_session.commit()

    assert db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).count() == 1


def test_new_draft_allowed_after_previous_one_rejected(db_session):
    """Дедуп проверяет только НЕзакрытые заявки — если предыдущая отклонена/отменена,
    новый активный случай может получить новый черновик."""
    channel, rc = _make_channel_and_case(db_session, "Состояние насоса")
    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW)
    db_session.flush()
    first = db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).one()
    first.status = MaintenanceRequestStatus.rejected
    db_session.flush()

    maybe_create_draft_request(db_session, PUMP_FAN_TRACK, channel, rc, FEATURES, proba=0.9, tick_end=NOW + dt.timedelta(hours=1))
    db_session.commit()

    assert db_session.query(MaintenanceRequest).filter_by(risk_case_id=rc.id).count() == 2
