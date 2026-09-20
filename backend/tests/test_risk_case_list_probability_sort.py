"""GET /risk-cases: вероятность последнего прогноза в списке и сортировка по ней
(раздел «Риски» админ-панели — диспетчер должен видеть и сортировать по вероятности
отказа прямо в таблице, не открывая каждую карточку)."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _make_case_with_predictions(db_session, ext_id: int, probabilities: list[float]) -> RiskCase:
    channel = Channel(external_channel_id=ext_id, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types="Состояние насоса", trained_at=NOW, train_period_start=NOW, train_period_end=NOW,
        is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, priority="medium", opened_at=NOW)
    db_session.add(rc)
    db_session.flush()
    for i, proba in enumerate(probabilities):
        db_session.add(
            Prediction(
                channel_id=channel.id,
                risk_case_id=rc.id,
                model_version_id=mv.id,
                category="sensor_failure_pump_fan",
                probability=proba,
                window_start=NOW,
                window_end=NOW,
                created_at=NOW + dt.timedelta(hours=i),
            )
        )
    db_session.commit()
    db_session.refresh(rc)
    return rc


def test_list_returns_latest_prediction_probability(client, db_session, auth_headers):
    rc = _make_case_with_predictions(db_session, 9101, [0.6, 0.75])
    r = client.get("/api/risk-cases", headers=auth_headers(UserRole.dispatcher))
    assert r.status_code == 200
    body = next(x for x in r.json() if x["id"] == rc.id)
    assert body["latest_probability"] == 0.75  # последний по времени, не первый/максимум


def test_sort_by_probability_desc(client, db_session, auth_headers):
    low = _make_case_with_predictions(db_session, 9102, [0.55])
    high = _make_case_with_predictions(db_session, 9103, [0.91])

    r = client.get("/api/risk-cases?sort_by=probability&sort_dir=desc", headers=auth_headers(UserRole.dispatcher))
    ids = [x["id"] for x in r.json()]
    assert ids.index(high.id) < ids.index(low.id)


def test_sort_by_probability_asc(client, db_session, auth_headers):
    low = _make_case_with_predictions(db_session, 9104, [0.55])
    high = _make_case_with_predictions(db_session, 9105, [0.91])

    r = client.get("/api/risk-cases?sort_by=probability&sort_dir=asc", headers=auth_headers(UserRole.dispatcher))
    ids = [x["id"] for x in r.json()]
    assert ids.index(low.id) < ids.index(high.id)
