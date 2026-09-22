"""Обучает CatBoost на газовых каналах с добавленными признаками сырой числовой телеметрии
(ml/experiments/build_features_газ_numeric.py) — проверка гипотезы, что динамика концентрации газа
несёт сигнал, которого нет в счётчиках переходов/тревог по состоянию (см. docstring
build_features_газ_numeric.py). Для честного сравнения обучены обе версии: только
state-признаки (как в ml/training/train_model_дым_газ.py, но подмножество "Газовый датчик") и
state + numeric-признаки — на одном и том же наборе строк.

Запуск: source .venv/bin/activate && python3 ml/experiments/train_model_газ_numeric.py
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent.parent
FEATURES_PARQUET = ROOT / "artifacts" / "features_газ_numeric_2024_2026.parquet"
OUT_REPORT = ROOT / "artifacts" / "model_report_газ_numeric.json"

TRAIN_END = pd.Timestamp("2025-01-01")
VAL_END = pd.Timestamp("2025-07-01")
GAP = pd.Timedelta(hours=24)

STATE_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]
NUMERIC_FEATURES = [
    "current_value",
    "avg_ppm_1h", "max_ppm_1h",
    "avg_ppm_24h", "max_ppm_24h",
    "avg_ppm_7d", "max_ppm_7d", "std_ppm_7d",
    "seconds_since_last_numeric",
    "zscore_7d",
]
CAT_FEATURES = ["current_state"]


def load_data() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{FEATURES_PARQUET}')").fetchdf()
    df = df.dropna(subset=["current_state"]).copy()
    df["frac_neighbors_in_fault"] = df["n_neighbors_in_fault"] / df["n_neighbors_total"].clip(lower=1)
    for c in NUMERIC_FEATURES:
        df[c] = df[c].astype(float)
    for c in CAT_FEATURES:
        df[c] = df[c].astype(str)
    return df


def split(df: pd.DataFrame):
    train = df[df["ts"] <= TRAIN_END - GAP]
    val = df[(df["ts"] >= TRAIN_END) & (df["ts"] <= VAL_END - GAP)]
    test = df[df["ts"] >= VAL_END]
    return train, val, test


def metrics_at_threshold(y_true, scores, thr):
    pred = scores >= thr
    tp = int(((pred) & (y_true == 1)).sum())
    fp = int(((pred) & (y_true == 0)).sum())
    fn = int(((~pred) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {"threshold": float(thr), "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall}


def pick_threshold(y_val, scores_val):
    precisions, recalls, thresholds = precision_recall_curve(y_val, scores_val)
    best = None
    for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds):
        if p > 0.7 and r > 0.5:
            if best is None or t < best:
                best = t
    return best


def evaluate_model(name, y_val, y_test, scores_val, scores_test):
    thr = pick_threshold(y_val, scores_val)
    result = {"model": name}
    if thr is None:
        result["threshold_found"] = False
    else:
        result["threshold_found"] = True
        result["threshold"] = float(thr)
        result["validation"] = metrics_at_threshold(y_val, scores_val, thr)
        result["test"] = metrics_at_threshold(y_test, scores_test, thr)
    result["roc_auc_val"] = float(roc_auc_score(y_val, scores_val))
    result["roc_auc_test"] = float(roc_auc_score(y_test, scores_test))
    result["pr_auc_val"] = float(average_precision_score(y_val, scores_val))
    result["pr_auc_test"] = float(average_precision_score(y_test, scores_test))
    return result


def train_and_eval(name, features, train, val, test, y_train, y_val, y_test):
    print(f"training {name} ({len(features)} features)...")
    train_pool = Pool(train[features], y_train, cat_features=CAT_FEATURES)
    val_pool = Pool(val[features], y_val, cat_features=CAT_FEATURES)
    test_pool = Pool(test[features], y_test, cat_features=CAT_FEATURES)

    model = CatBoostClassifier(
        iterations=1000, depth=6, learning_rate=0.05,
        loss_function="Logloss", eval_metric="AUC",
        auto_class_weights="Balanced", early_stopping_rounds=100,
        random_seed=42, verbose=False,
    )
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    scores_val = model.predict_proba(val_pool)[:, 1]
    scores_test = model.predict_proba(test_pool)[:, 1]
    result = evaluate_model(name, y_val, y_test, scores_val, scores_test)
    result["feature_importance"] = dict(
        zip(features, [float(x) for x in model.get_feature_importance(train_pool)])
    )
    result["best_iteration"] = model.get_best_iteration()

    model.save_model(str(ROOT / "artifacts" / f"catboost_{name}.cbm"))
    scored = pd.concat(
        [
            val[["channel_id", "ts", "y_true"]].assign(score=scores_val, split="val"),
            test[["channel_id", "ts", "y_true"]].assign(score=scores_test, split="test"),
        ],
        ignore_index=True,
    )
    scored.to_parquet(ROOT / "artifacts" / f"scored_{name}.parquet")
    return result


def main() -> None:
    print("loading feature table...")
    df = load_data()
    # только строки, где числовая телеметрия реально была известна на момент t (честное сравнение)
    df = df[df["current_value"].notna()].copy()
    train, val, test = split(df)
    print(f"train={len(train)} val={len(val)} test={len(test)}")
    print(f"train positives={train.y_true.sum()} val positives={val.y_true.sum()} test positives={test.y_true.sum()}")

    y_train = train["y_true"].astype(int).values
    y_val = val["y_true"].astype(int).values
    y_test = test["y_true"].astype(int).values

    state_only = train_and_eval(
        "газ_state_only", STATE_FEATURES + CAT_FEATURES, train, val, test, y_train, y_val, y_test
    )
    state_plus_numeric = train_and_eval(
        "газ_state_plus_numeric", STATE_FEATURES + NUMERIC_FEATURES + CAT_FEATURES,
        train, val, test, y_train, y_val, y_test,
    )

    report = {
        "train_end": str(TRAIN_END), "val_end": str(VAL_END), "gap_hours": 24,
        "n_train": len(train), "n_val": len(val), "n_test": len(test),
        "n_train_positive": int(y_train.sum()), "n_val_positive": int(y_val.sum()),
        "n_test_positive": int(y_test.sum()),
        "target_precision": 0.7, "target_recall": 0.5,
        "state_only": state_only,
        "state_plus_numeric": state_plus_numeric,
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {k: v for k, v in report.items() if k not in ("state_only", "state_plus_numeric")},
        ensure_ascii=False, indent=2,
    ))
    print("state_only:", {k: v for k, v in state_only.items() if k != "feature_importance"})
    print("state_plus_numeric:", {k: v for k, v in state_plus_numeric.items() if k != "feature_importance"})
    print(f"saved report to {OUT_REPORT}")


if __name__ == "__main__":
    main()
