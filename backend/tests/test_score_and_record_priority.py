"""score_and_record: приоритет нового риск-кейса эскалируется до high не только при
proba>=0.85, но и когда независимая от CatBoost модель (IsolationForest) отдельно
отмечает поведение канала как аномальное — два независимых метода согласны, это сильнее
одного порога вероятности (см. backend/app/workers/replay_worker.py:score_and_record)."""
import datetime as dt

import numpy as np

from app.models.entities import Channel, ModelVersion, RiskCase
from app.workers.replay_worker import ALL_FEATURES, NUM_FEATURES, TRACKS, score_and_record

PUMP_FAN_TRACK = TRACKS[0]
PUMP_FAN_THRESHOLD = 0.55
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

FEATURES = {
    "n_alarms_1h": 0, "n_alarms_24h": 0, "n_alarms_7d": 1,
    "n_transitions_1h": 0, "n_transitions_24h": 1, "n_transitions_7d": 2,
    "n_events_1h": 0, "n_events_24h": 1, "n_events_7d": 3,
    "seconds_since_last_event": 100.0,
    "n_neighbors_in_fault": 0, "frac_neighbors_in_fault": 0.0,
    "current_state": "Неисправен",
}


class FakeCatBoost:
    """Заглушка вместо обученного CatBoost: фиксированная вероятность, нулевые SHAP."""

    def __init__(self, proba: float):
        self._proba = proba

    def predict_proba(self, row):
        return [[1 - self._proba, self._proba]]

    def get_feature_importance(self, pool, type=None):
        return np.zeros((1, len(ALL_FEATURES) + 1))


class FakeIsolationForest:
    def __init__(self, is_outlier: bool):
        self._is_outlier = is_outlier

    def decision_function(self, x):
        return [0.0]

    def predict(self, x):
        return [-1 if self._is_outlier else 1]


def _setup(db_session, sensor_type="Состояние насоса"):
    channel = Channel(external_channel_id=8001, sensor_type=sensor_type)
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types=sensor_type, trained_at=NOW, train_period_start=NOW, train_period_end=NOW,
        is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    return channel, mv


def test_moderate_probability_without_anomaly_is_medium_priority(db_session):
    channel, mv = _setup(db_session)
    anomaly_bundle = {"model": FakeIsolationForest(is_outlier=False), "features": NUM_FEATURES}

    score_and_record(db_session, PUMP_FAN_TRACK, PUMP_FAN_THRESHOLD, FakeCatBoost(0.6), anomaly_bundle, channel, FEATURES, NOW, mv.id)
    db_session.commit()

    rc = db_session.query(RiskCase).filter_by(channel_id=channel.id).one()
    assert rc.priority == "medium"


def test_moderate_probability_with_anomaly_is_escalated_to_high(db_session):
    channel, mv = _setup(db_session)
    anomaly_bundle = {"model": FakeIsolationForest(is_outlier=True), "features": NUM_FEATURES}

    score_and_record(db_session, PUMP_FAN_TRACK, PUMP_FAN_THRESHOLD, FakeCatBoost(0.6), anomaly_bundle, channel, FEATURES, NOW, mv.id)
    db_session.commit()

    rc = db_session.query(RiskCase).filter_by(channel_id=channel.id).one()
    assert rc.priority == "high"


def test_priority_is_not_recomputed_for_already_open_risk_case(db_session):
    """Приоритет решается один раз при открытии — последующие тики с аномалией не должны
    задним числом менять уже назначенный приоритет открытого риск-кейса."""
    channel, mv = _setup(db_session)
    calm_bundle = {"model": FakeIsolationForest(is_outlier=False), "features": NUM_FEATURES}
    anomalous_bundle = {"model": FakeIsolationForest(is_outlier=True), "features": NUM_FEATURES}

    score_and_record(db_session, PUMP_FAN_TRACK, PUMP_FAN_THRESHOLD, FakeCatBoost(0.6), calm_bundle, channel, FEATURES, NOW, mv.id)
    db_session.commit()
    score_and_record(
        db_session, PUMP_FAN_TRACK, PUMP_FAN_THRESHOLD, FakeCatBoost(0.6), anomalous_bundle, channel, FEATURES,
        NOW + dt.timedelta(hours=1), mv.id,
    )
    db_session.commit()

    rc = db_session.query(RiskCase).filter_by(channel_id=channel.id).one()
    assert rc.priority == "medium"
