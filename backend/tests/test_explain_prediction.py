"""SHAP-объяснение конкретного прогноза (не глобальная важность) — раздел «модели»
админ-панели: у каждого сохранённого прогноза, перешедшего порог, теперь есть top-5
признаков с их вкладом, посчитанным той же моделью, что и сам прогноз."""
from pathlib import Path

import pytest
from catboost import CatBoostClassifier

from app.ml.explain import explain_prediction
from app.ml.features import ALL_FEATURES

MODEL_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "catboost_насос_вентилятор.cbm"


@pytest.fixture(scope="module")
def model() -> CatBoostClassifier:
    if not MODEL_PATH.exists():
        pytest.skip(f"обученная модель не найдена: {MODEL_PATH}")
    m = CatBoostClassifier()
    m.load_model(str(MODEL_PATH))
    return m


def _sample_row() -> list[list]:
    values = {
        "n_alarms_1h": 0, "n_alarms_24h": 0, "n_alarms_7d": 2,
        "n_transitions_1h": 0, "n_transitions_24h": 0, "n_transitions_7d": 1,
        "n_events_1h": 0, "n_events_24h": 1, "n_events_7d": 5,
        "seconds_since_last_event": 3600.0,
        "n_neighbors_in_fault": 1, "frac_neighbors_in_fault": 0.5,
        "current_state": "Неисправен", "тип_датчика": "Состояние насоса",
    }
    return [[values[f] for f in ALL_FEATURES]]


def test_explain_prediction_returns_top_five_signed_contributions(model):
    result = explain_prediction(model, _sample_row())
    assert result["method"] == "catboost_shap"
    assert isinstance(result["base_value"], float)
    assert len(result["top_features"]) == 5
    contributions = [abs(f["contribution"]) for f in result["top_features"]]
    assert contributions == sorted(contributions, reverse=True)
    for f in result["top_features"]:
        assert f["feature"] in ALL_FEATURES
        assert f["label"]


def test_explain_prediction_is_per_sample_not_global(model):
    """Разные входы -> разные объяснения (иначе это снова глобальная важность, не SHAP)."""
    calm_row = [[0, 0, 0, 0, 0, 0, 0, 0, 0, 999999.0, 0, 0.0, "Исправен", "Состояние насоса"]]
    alarming_row = _sample_row()

    calm = explain_prediction(model, calm_row)
    alarming = explain_prediction(model, alarming_row)

    assert calm["top_features"] != alarming["top_features"]
