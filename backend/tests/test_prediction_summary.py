"""GET /predictions/{id}/summary. generate_dispatcher_summary раньше вызывалась даже когда
llm_summary уже пересчитывался параллельным запросом за то же время — теперь обёрнуто в
SELECT ... FOR UPDATE, второй запрос должен увидеть уже посчитанный результат, а не дёрнуть
LLM API повторно (см. app/api/predictions.py:get_prediction_summary)."""
import datetime as dt
from unittest.mock import patch

from app.api.predictions import get_prediction_summary
from app.core.db import SessionLocal
from app.models.entities import Channel, ModelVersion, Prediction, RiskCase, User
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


def test_concurrent_calls_see_committed_summary_not_stale_none(db_session):
    """APP-03: два запроса карточки одного прогноза почти одновременно, две настоящие сессии
    БД. Session A успевает загрузить Prediction (identity map хранит llm_summary=None) ДО
    того, как Session B посчитала и закоммитила своё резюме. Без populate_existing() в
    get_prediction_summary повторный SELECT ... FOR UPDATE в Session A вернул бы ТОТ ЖЕ
    Python-объект с устаревшим None из identity map вместо свежей строки из БД — LLM был бы
    вызван повторно вместо использования уже посчитанного Session B результата."""
    prediction = _setup(db_session)
    user = User(username="race-summary", password_hash="x", role=UserRole.admin)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    session_a = SessionLocal()
    try:
        loaded = session_a.get(Prediction, prediction.id)
        assert loaded.llm_summary is None  # identity map "отравлена" старым значением

        session_b = SessionLocal()
        try:
            b_pred = session_b.get(Prediction, prediction.id)
            b_pred.llm_summary = "резюме от параллельной сессии"
            session_b.commit()
        finally:
            session_b.close()

        with patch("app.api.predictions.generate_dispatcher_summary") as mocked:
            result = get_prediction_summary(prediction_id=prediction.id, db=session_a, user=user)

        assert result == {"summary": "резюме от параллельной сессии"}
        mocked.assert_not_called()
    finally:
        session_a.close()
