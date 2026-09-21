"""GET /predictions?risk_case_id=... — исправление бага, при котором RiskCard.tsx показывал
для закрытого риск-кейса ПОСЛЕДНИЙ прогноз воркера по каналу вообще (текущий тик), а не тот,
что реально был при открытии именно этого кейса, если после закрытия по каналу появлялись
новые прогнозы (в т.ч. с другой вероятностью, привязанные к другому/новому риск-кейсу)."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)


def _setup(db_session):
    channel = Channel(external_channel_id=77001, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types="Состояние насоса", trained_at=NOW,
        train_period_start=NOW, train_period_end=NOW, is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    return channel, mv


def _prediction(channel, mv, risk_case, probability, created_at):
    return Prediction(
        channel_id=channel.id, risk_case_id=risk_case.id if risk_case else None, model_version_id=mv.id,
        category="sensor_failure_pump_fan", probability=probability,
        window_start=created_at, window_end=created_at + dt.timedelta(hours=24),
        created_at=created_at,
    )


def test_predictions_filtered_by_risk_case_id_ignores_newer_unrelated_predictions(
    client, db_session, auth_headers
):
    channel, mv = _setup(db_session)
    old_case = RiskCase(
        channel_id=channel.id, status=RiskCaseStatus.resolved,
        opened_at=NOW - dt.timedelta(days=60), closed_at=NOW - dt.timedelta(days=59),
    )
    new_case = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=NOW)
    db_session.add_all([old_case, new_case])
    db_session.flush()

    db_session.add(_prediction(channel, mv, old_case, 0.62, NOW - dt.timedelta(days=59)))
    # Более новый прогноз того же канала, но привязанный к ДРУГОМУ риск-кейсу — без
    # risk_case_id-фильтра он "перебивал" бы старый при запросе по channel_id+category.
    db_session.add(_prediction(channel, mv, new_case, 0.57, NOW))
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get(f"/api/predictions?risk_case_id={old_case.id}&limit=1", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["risk_case_id"] == old_case.id
    assert body[0]["probability"] == 0.62


def test_latest_per_case_collapses_hourly_ticks_to_one_row_per_case(client, db_session, auth_headers):
    """Журнал прогнозов (JournalPage.tsx) раньше показывал сырой поток всех почасовых
    тиков — в основном без реального SHAP (backfill_shap_explanations.py считает его только
    для последнего прогноза каждого кейса). latest_per_case=true должен вернуть ровно один,
    самый свежий, прогноз на риск-кейс."""
    channel, mv = _setup(db_session)
    case = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=NOW - dt.timedelta(hours=5))
    db_session.add(case)
    db_session.flush()

    for i, proba in enumerate([0.55, 0.60, 0.70, 0.80]):
        db_session.add(_prediction(channel, mv, case, proba, NOW - dt.timedelta(hours=4 - i)))
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/predictions?latest_per_case=true", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["risk_case_id"] == case.id
    assert body[0]["probability"] == 0.80
    assert int(r.headers["X-Total-Count"]) == 1


def test_latest_per_case_ignores_predictions_without_risk_case(client, db_session, auth_headers):
    channel, mv = _setup(db_session)
    db_session.add(_prediction(channel, mv, None, 0.9, NOW))
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/predictions?latest_per_case=true", headers=headers)
    assert r.status_code == 200
    assert r.json() == []
    assert int(r.headers["X-Total-Count"]) == 0
