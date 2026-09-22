"""Обучает базовую линию и CatBoost на ДНЕВНОЙ витрине признаков
(scripts/build_features_daily.py) — эксперимент по гипотезе «дневная гранулярность» из
docs/documentation/analysis/model_report_насос_вентилятор.md, раздел 5. Тот же протокол train/val/test
и разрыв 24ч, что и в scripts/train_model.py, но окна признаков 1д/7д/30д вместо 1ч/24ч/7сут.

Запуск: source .venv/bin/activate && python3 scripts/train_model_daily.py
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
FEATURES_PARQUET = ROOT / "docs" / "documentation" / "analysis" / "features_насос_вентилятор_daily_2024_2026.parquet"
OUT_REPORT = ROOT / "docs" / "documentation" / "analysis" / "model_report_насос_вентилятор_daily.json"

TRAIN_END = pd.Timestamp("2025-01-01")
VAL_END = pd.Timestamp("2025-07-01")
GAP = pd.Timedelta(hours=24)

NUM_FEATURES = [
    "n_alarms_1d", "n_alarms_7d", "n_alarms_30d",
    "n_transitions_1d", "n_transitions_7d", "n_transitions_30d",
    "n_events_1d", "n_events_7d", "n_events_30d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]
CAT_FEATURES = ["current_state", "тип_датчика"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES


def load_data() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{FEATURES_PARQUET}')").fetchdf()
    df = df.dropna(subset=["current_state"]).copy()
    df["frac_neighbors_in_fault"] = df["n_neighbors_in_fault"] / df["n_neighbors_total"].clip(lower=1)
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
    """Наименьший порог на validation, одновременно дающий Precision>0.7 и Recall>0.5."""
    precisions, recalls, thresholds = precision_recall_curve(y_val, scores_val)
    best = None
    for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds):
        if p > 0.7 and r > 0.5:
            if best is None or t < best:
                best = t
    return best


def evaluate_model(name, y_train, y_val, y_test, scores_train, scores_val, scores_test):
    thr = pick_threshold(y_val, scores_val)
    result = {"model": name}
    if thr is None:
        result["threshold_found"] = False
        precisions, recalls, thresholds = precision_recall_curve(y_val, scores_val)
        idx = np.argsort(-recalls[:-1])
        sample = [
            {"threshold": float(thresholds[i]), "precision": float(precisions[i]), "recall": float(recalls[i])}
            for i in idx[:: max(1, len(idx) // 10)][:10]
        ]
        result["validation_pr_sample"] = sample
    else:
        result["threshold_found"] = True
        result["threshold"] = float(thr)
        result["validation"] = metrics_at_threshold(y_val, scores_val, thr)
        result["test"] = metrics_at_threshold(y_test, scores_test, thr)
    return result


def main() -> None:
    print("loading feature table...")
    df = load_data()
    train, val, test = split(df)
    print(f"train={len(train)} val={len(val)} test={len(test)}")
    print(f"train positives={train.y_true.sum()} val positives={val.y_true.sum()} test positives={test.y_true.sum()}")

    y_train = train["y_true"].astype(int).values
    y_val = val["y_true"].astype(int).values
    y_test = test["y_true"].astype(int).values

    # --- Базовая линия: частота переключений за последний день ---
    baseline_train = train["n_transitions_1d"].astype(float).values
    baseline_val = val["n_transitions_1d"].astype(float).values
    baseline_test = test["n_transitions_1d"].astype(float).values
    baseline_result = evaluate_model(
        "baseline_n_transitions_1d", y_train, y_val, y_test,
        baseline_train, baseline_val, baseline_test,
    )

    # --- CatBoost ---
    print("training CatBoost...")
    train_pool = Pool(train[ALL_FEATURES], y_train, cat_features=CAT_FEATURES)
    val_pool = Pool(val[ALL_FEATURES], y_val, cat_features=CAT_FEATURES)
    test_pool = Pool(test[ALL_FEATURES], y_test, cat_features=CAT_FEATURES)

    model = CatBoostClassifier(
        iterations=1000,
        depth=6,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="AUC",
        auto_class_weights="Balanced",
        early_stopping_rounds=100,
        random_seed=42,
        verbose=False,
    )
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    scores_train = model.predict_proba(train_pool)[:, 1]
    scores_val = model.predict_proba(val_pool)[:, 1]
    scores_test = model.predict_proba(test_pool)[:, 1]
    catboost_result = evaluate_model(
        "catboost", y_train, y_val, y_test, scores_train, scores_val, scores_test
    )
    catboost_result["feature_importance"] = dict(
        zip(ALL_FEATURES, [float(x) for x in model.get_feature_importance(train_pool)])
    )
    catboost_result["best_iteration"] = model.get_best_iteration()
    catboost_result["roc_auc_val"] = float(roc_auc_score(y_val, scores_val))
    catboost_result["roc_auc_test"] = float(roc_auc_score(y_test, scores_test))
    catboost_result["pr_auc_val"] = float(average_precision_score(y_val, scores_val))
    catboost_result["pr_auc_test"] = float(average_precision_score(y_test, scores_test))
    baseline_result["roc_auc_val"] = float(roc_auc_score(y_val, baseline_val))
    baseline_result["pr_auc_val"] = float(average_precision_score(y_val, baseline_val))

    model.save_model(str(ROOT / "docs" / "documentation" / "analysis" / "catboost_насос_вентилятор_daily.cbm"))
    scored = pd.concat(
        [
            val[["channel_id", "ts", "y_true"]].assign(score=scores_val, split="val"),
            test[["channel_id", "ts", "y_true"]].assign(score=scores_test, split="test"),
        ],
        ignore_index=True,
    )
    scored.to_parquet(ROOT / "docs" / "documentation" / "analysis" / "scored_насос_вентилятор_daily.parquet")

    report = {
        "train_end": str(TRAIN_END), "val_end": str(VAL_END), "gap_hours": 24,
        "grid": "daily",
        "n_train": len(train), "n_val": len(val), "n_test": len(test),
        "n_train_positive": int(y_train.sum()), "n_val_positive": int(y_val.sum()),
        "n_test_positive": int(y_test.sum()),
        "target_precision": 0.7, "target_recall": 0.5,
        "baseline": baseline_result,
        "catboost": catboost_result,
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"saved report to {OUT_REPORT}")


if __name__ == "__main__":
    main()
