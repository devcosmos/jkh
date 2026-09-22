"""IsolationForest как независимый от CatBoost сигнал аномальности (ml/training/train_anomaly_model.py):
без учителя, на тех же поведенческих признаках, обнаруживает необычное поведение канала, а не
только уже виденные в разметке сценарии отказа."""
from pathlib import Path

import joblib
import pytest

from app.workers.replay_worker import NUM_FEATURES, compute_anomaly_signal

BUNDLE_PATH = Path(__file__).resolve().parents[2] / "docs" / "documentation" / "analysis" / "isolation_forest_насос_вентилятор.joblib"


@pytest.fixture(scope="module")
def anomaly_bundle() -> dict:
    if not BUNDLE_PATH.exists():
        pytest.skip(f"обученная модель аномалий не найдена: {BUNDLE_PATH}")
    return joblib.load(BUNDLE_PATH)


def _calm_features() -> dict:
    return {
        "n_alarms_1h": 0, "n_alarms_24h": 0, "n_alarms_7d": 0,
        "n_transitions_1h": 0, "n_transitions_24h": 0, "n_transitions_7d": 0,
        "n_events_1h": 0, "n_events_24h": 1, "n_events_7d": 3,
        "seconds_since_last_event": 3600.0,
        "n_neighbors_in_fault": 0, "frac_neighbors_in_fault": 0.0,
    }


def _extreme_features() -> dict:
    return {
        "n_alarms_1h": 500, "n_alarms_24h": 5000, "n_alarms_7d": 30000,
        "n_transitions_1h": 500, "n_transitions_24h": 5000, "n_transitions_7d": 30000,
        "n_events_1h": 500, "n_events_24h": 5000, "n_events_7d": 30000,
        "seconds_since_last_event": 0.0,
        "n_neighbors_in_fault": 50, "frac_neighbors_in_fault": 1.0,
    }


def test_compute_anomaly_signal_uses_only_numeric_features(anomaly_bundle):
    assert anomaly_bundle["features"] == NUM_FEATURES


def test_extreme_behavior_scores_more_anomalous_than_calm(anomaly_bundle):
    calm = compute_anomaly_signal(anomaly_bundle, _calm_features())
    extreme = compute_anomaly_signal(anomaly_bundle, _extreme_features())

    assert calm["method"] == "isolation_forest"
    assert extreme["score"] < calm["score"]  # ниже score = более аномально
    assert extreme["is_outlier"] is True
