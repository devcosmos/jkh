"""GET /predictions/{id}/summary. generate_dispatcher_summary раньше вызывалась даже когда
llm_summary уже пересчитывался параллельным запросом за то же время — теперь обёрнуто в
SELECT ... FOR UPDATE, второй запрос должен увидеть уже посчитанный результат, а не дёрнуть
LLM API повторно (см. app/api/predictions.py:get_prediction_summary)."""
import datetime as dt
from unittest.mock import patch

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)


def _setup(db_session) -> Prediction:
    channel = Channel(external_channel_id=77501, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types="Состояние насоса", trained_at=NOW,
        train_period_start=NOW, train_period_end=NOW, is_active=True,
    )
    db_session.add(mv)
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, priority="medium", opened_at=NOW)
    db_session.add(rc)
    db_session.flush()
    prediction = Prediction(
        channel_id=channel.id, risk_case_id=rc.id, model_version_id=mv.id,
        category="sensor_failure_pump_fan", probability=0.7,
        window_start=NOW, window_end=NOW + dt.timedelta(hours=24), created_at=NOW,
        explanation={"top_features": [{"label": "x", "value": 1, "contribution": 0.1}]},
    )
    db_session.add(prediction)
    db_session.commit()
    db_session.refresh(prediction)
    return prediction


def test_returns_cached_summary_without_calling_llm(client, db_session, auth_headers):
    prediction = _setup(db_session)
    prediction.llm_summary = "уже посчитанное резюме"
    db_session.commit()

    with patch("app.api.predictions.generate_dispatcher_summary") as mocked:
        r = client.get(f"/api/predictions/{prediction.id}/summary", headers=auth_headers(UserRole.dispatcher))

    assert r.status_code == 200
    assert r.json()["summary"] == "уже посчитанное резюме"
    mocked.assert_not_called()


def test_no_api_key_returns_none_without_crashing(client, db_session, auth_headers):
    prediction = _setup(db_session)

    r = client.get(f"/api/predictions/{prediction.id}/summary", headers=auth_headers(UserRole.dispatcher))

    assert r.status_code == 200
    assert r.json()["summary"] is None


def test_result_is_cached_after_first_successful_call(client, db_session, auth_headers):
    prediction = _setup(db_session)

    with patch("app.api.predictions.generate_dispatcher_summary", return_value="новое резюме") as mocked:
        r1 = client.get(f"/api/predictions/{prediction.id}/summary", headers=auth_headers(UserRole.dispatcher))
        assert r1.json()["summary"] == "новое резюме"
        assert mocked.call_count == 1

        r2 = client.get(f"/api/predictions/{prediction.id}/summary", headers=auth_headers(UserRole.dispatcher))
        assert r2.json()["summary"] == "новое резюме"
        assert mocked.call_count == 1  # второй запрос не дёргает LLM снова — уже закешировано
