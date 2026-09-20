"""Новые разделы админ-панели (дашборд, реестр каналов, журнал аудита, пользователи) —
проверка прав доступа и базовой корректности агрегатов, без выдуманных данных."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Object, Prediction, ReplayState, RiskCase
from app.models.enums import RiskCaseStatus, UserRole


def test_dashboard_summary_counts_open_risk_cases(client, db_session, auth_headers):
    obj = Object(name="Объект для дашборда")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=5001, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    db_session.add(
        RiskCase(
            channel_id=channel.id,
            status=RiskCaseStatus.new,
            priority="high",
            category="sensor_failure_pump_fan",
            opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/dashboard/summary", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["risk_cases"]["total_open"] == 1
    assert body["risk_cases"]["by_category"]["sensor_failure_pump_fan"] == 1
    assert body["risk_cases"]["open_with_anomaly"] == 0
    assert body["top_objects"][0]["object_id"] == obj.id


def test_dashboard_summary_counts_anomaly_flagged_open_cases(client, db_session, auth_headers):
    obj = Object(name="Объект с аномалией")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=5201, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(
        channel_id=channel.id,
        status=RiskCaseStatus.new,
        priority="high",
        category="sensor_failure_pump_fan",
        opened_at=dt.datetime.now(dt.timezone.utc),
    )
    db_session.add(rc)
    db_session.flush()
    mv = ModelVersion(
        name="test-model",
        sensor_types="Состояние насоса",
        trained_at=dt.datetime.now(dt.timezone.utc),
        train_period_start=dt.datetime.now(dt.timezone.utc),
        train_period_end=dt.datetime.now(dt.timezone.utc),
        is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    db_session.add(
        Prediction(
            channel_id=channel.id,
            risk_case_id=rc.id,
            model_version_id=mv.id,
            category="sensor_failure_pump_fan",
            probability=0.9,
            window_start=dt.datetime.now(dt.timezone.utc),
            window_end=dt.datetime.now(dt.timezone.utc),
            explanation={"anomaly": {"method": "isolation_forest", "score": -0.1, "is_outlier": True}},
        )
    )
    db_session.commit()

    r = client.get("/api/dashboard/summary", headers=auth_headers(UserRole.dispatcher))
    assert r.json()["risk_cases"]["open_with_anomaly"] == 1


def test_channels_list_filters_by_sensor_type(client, db_session, auth_headers):
    obj = Object(name="Объект с каналами")
    db_session.add(obj)
    db_session.flush()
    db_session.add_all(
        [
            Channel(external_channel_id=5101, sensor_type="Состояние насоса", object_id=obj.id),
            Channel(external_channel_id=5102, sensor_type="Датчик дыма", object_id=obj.id),
        ]
    )
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/channels?sensor_type=Датчик дыма", headers=headers)
    assert r.status_code == 200
    assert [c["external_channel_id"] for c in r.json()] == [5102]


def test_audit_log_requires_admin(client, auth_headers):
    r = client.get("/api/audit-log", headers=auth_headers(UserRole.dispatcher))
    assert r.status_code == 403

    r = client.get("/api/audit-log", headers=auth_headers(UserRole.admin))
    assert r.status_code == 200


def test_users_list_and_create_requires_admin(client, auth_headers):
    dispatcher_headers = auth_headers(UserRole.dispatcher)
    assert client.get("/api/access/users", headers=dispatcher_headers).status_code == 403

    admin_headers = auth_headers(UserRole.admin)
    r = client.post(
        "/api/access/users",
        json={"username": "new-dispatcher", "password": "test-pass-123", "role": "dispatcher"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    assert r.json()["username"] == "new-dispatcher"

    r = client.get("/api/access/users", headers=admin_headers)
    usernames = {u["username"] for u in r.json()}
    assert "new-dispatcher" in usernames


def test_create_user_rejects_duplicate_username(client, auth_headers):
    admin_headers = auth_headers(UserRole.admin, username="dup-admin")
    payload = {"username": "dup-admin", "password": "test-pass-123", "role": "dispatcher"}
    r = client.post("/api/access/users", json=payload, headers=admin_headers)
    assert r.status_code == 409


def test_dashboard_summary_reports_worker_liveness(client, db_session, auth_headers):
    now = dt.datetime.now(dt.timezone.utc)
    db_session.add(ReplayState(id=1, virtual_time=now - dt.timedelta(hours=2), updated_at=now))
    db_session.commit()

    r = client.get("/api/dashboard/summary", headers=auth_headers(UserRole.dispatcher))
    worker = r.json()["worker"]
    assert worker["is_stale"] is False
    assert worker["seconds_since_update"] < 5


def test_dashboard_summary_flags_stale_worker(client, db_session, auth_headers):
    now = dt.datetime.now(dt.timezone.utc)
    db_session.add(ReplayState(id=1, virtual_time=now, updated_at=now - dt.timedelta(minutes=20)))
    db_session.commit()

    r = client.get("/api/dashboard/summary", headers=auth_headers(UserRole.dispatcher))
    assert r.json()["worker"]["is_stale"] is True


def test_dashboard_summary_daily_volume_counts_opened_and_closed(client, db_session, auth_headers):
    obj = Object(name="Объект для суточного объёма")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=5301, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    day = dt.datetime(2026, 5, 1, 10, 0, tzinfo=dt.timezone.utc)
    db_session.add(RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=day))
    db_session.add(
        RiskCase(
            channel_id=channel.id, status=RiskCaseStatus.resolved,
            opened_at=day - dt.timedelta(days=1), closed_at=day,
        )
    )
    db_session.commit()

    r = client.get("/api/dashboard/summary", headers=auth_headers(UserRole.dispatcher))
    row = next(x for x in r.json()["daily_volume"] if x["date"] == "2026-05-01")
    assert row["opened"] == 1
    assert row["closed"] == 1
