"""X-Total-Count на списковых эндпоинтах — без него фронт не может построить постраничную
навигацию (знать, сколько всего строк за пределами текущей выдачи limit/offset). См.
docs/Статус.md, запись 21 сентября: раньше все страницы админки показывали только первые
N строк без способа посмотреть остальное."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)


def test_risk_cases_total_count_ignores_limit(client, db_session, auth_headers):
    channel = Channel(external_channel_id=88001, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    for i in range(5):
        db_session.add(RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=NOW))
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/risk-cases?limit=2", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert int(r.headers["X-Total-Count"]) == 5


def test_predictions_total_count(client, db_session, auth_headers):
    channel = Channel(external_channel_id=88002, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="t", sensor_types="Состояние насоса", trained_at=NOW,
        train_period_start=NOW, train_period_end=NOW, is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    for i in range(3):
        db_session.add(
            Prediction(
                channel_id=channel.id, model_version_id=mv.id, category="sensor_failure_pump_fan",
                probability=0.6, window_start=NOW, window_end=NOW + dt.timedelta(hours=24), created_at=NOW,
            )
        )
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/predictions?channel_id=" + str(channel.id) + "&limit=1", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert int(r.headers["X-Total-Count"]) == 3


def test_channels_total_count(client, db_session, auth_headers):
    for i in range(4):
        db_session.add(Channel(external_channel_id=88100 + i, sensor_type="Датчик дыма"))
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/channels?sensor_type=Датчик дыма&limit=2", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert int(r.headers["X-Total-Count"]) == 4


def test_audit_log_total_count(client, db_session, auth_headers):
    headers = auth_headers(UserRole.admin)
    for i in range(3):
        client.post(
            "/api/access/users",
            json={"username": f"pgtest{i}", "password": "test-pass-123", "role": "analyst"},
            headers=headers,
        )
    r = client.get("/api/audit-log?limit=1", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert int(r.headers["X-Total-Count"]) >= 3
