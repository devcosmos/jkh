"""Объяснение прогноза: SHAP по CatBoost (per-tick, той же моделью, что и сам прогноз) и
независимый сигнал аномальности (IsolationForest без учителя, обучен в
ml/training/train_anomaly_model.py — офлайн-пайплайн в корне репозитория, не импортируется
отсюда). Вынесено из app/workers/replay_worker.py реструктуризацией каталогов (шаг 3).
"""
from catboost import CatBoostClassifier, Pool

from app.ml.features import ALL_FEATURES, CAT_FEATURE_IDX, FEATURE_LABELS


def explain_prediction(model: CatBoostClassifier, row: list[list]) -> dict:
    """SHAP-объяснение конкретного прогноза (не глобальная важность признаков) —
    per-tick, той же моделью, что и сам прогноз (get_feature_importance(..., ShapValues)).
    Топ-5 признаков по модулю вклада, со знаком (в сторону риска / против)."""
    pool = Pool(row, cat_features=CAT_FEATURE_IDX)
    shap_row = model.get_feature_importance(pool, type="ShapValues")[0]
    base_value = float(shap_row[-1])
    contributions = list(zip(ALL_FEATURES, shap_row[:-1], row[0]))
    contributions.sort(key=lambda t: abs(t[1]), reverse=True)
    return {
        "method": "catboost_shap",
        "base_value": round(base_value, 4),
        "top_features": [
            {
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                "value": round(float(value), 3) if isinstance(value, (int, float)) else str(value),
                "contribution": round(float(contribution), 4),
            }
            for name, contribution, value in contributions[:5]
        ],
    }


def compute_anomaly_signal(anomaly_bundle: dict, features: dict) -> dict:
    """Независимый от CatBoost сигнал: IsolationForest без учителя на тех же поведенческих
    признаках (ml/training/train_anomaly_model.py). Не заменяет прогноз модели, а дополняет его —
    может отметить необычное поведение канала, не похожее ни на один известный сценарий
    отказа в разметке (в отличие от CatBoost, который находит только виденные паттерны)."""
    model = anomaly_bundle["model"]
    feature_names = anomaly_bundle["features"]
    x = [[features[f] for f in feature_names]]
    score = float(model.decision_function(x)[0])  # выше — более «нормально»
    is_outlier = bool(model.predict(x)[0] == -1)
    return {"method": "isolation_forest", "score": round(score, 4), "is_outlier": is_outlier}
