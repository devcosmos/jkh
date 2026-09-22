"""ML-08 (analys_and_todo.md): пересчитывает scored_<track>.parquet ТЕКУЩЕЙ развёрнутой
моделью (artifacts/catboost_<track>.cbm) на актуальной витрине признаков — БЕЗ переобучения.

Нужен, чтобы измерить фактический эффект правок витрины (например, тай-брейк одинаковых
timestamp — Технические_заметки.md, запись от 22 сентября) на метрики самим числом, а не
предположением "изменение малó, переобучение не требуется". Прежний scored_<track>.parquet
получен той же моделью на старой (до тай-брейка) витрине — after run
ml/evaluation/evaluate_episodes*.py покажет разницу.

Использует тот же train/val/test split и список признаков, что ml/training/train_model*.py.

Запуск: source .venv/bin/activate && python3 ml/evaluation/rescore_deployed_model.py --track насос_вентилятор
        source .venv/bin/activate && python3 ml/evaluation/rescore_deployed_model.py --track дым_газ
"""
import argparse
from pathlib import Path

import duckdb
import pandas as pd
from catboost import CatBoostClassifier

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"

TRAIN_END = pd.Timestamp("2025-01-01")
VAL_END = pd.Timestamp("2025-07-01")
GAP = pd.Timedelta(hours=24)

NUM_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]
CAT_FEATURES = ["current_state", "тип_датчика"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--track", required=True, choices=["насос_вентилятор", "дым_газ"])
    args = p.parse_args()
    track = args.track

    features_path = ARTIFACTS_DIR / f"features_{track}_2024_2026.parquet"
    model_path = ARTIFACTS_DIR / f"catboost_{track}.cbm"
    out_path = ARTIFACTS_DIR / f"scored_{track}.parquet"

    print(f"[{track}] loading {features_path}...")
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{features_path}')").fetchdf()
    df = df.dropna(subset=["current_state"]).copy()
    df["frac_neighbors_in_fault"] = df["n_neighbors_in_fault"] / df["n_neighbors_total"].clip(lower=1)
    for c in CAT_FEATURES:
        df[c] = df[c].astype(str)

    val = df[(df["ts"] >= TRAIN_END) & (df["ts"] <= VAL_END - GAP)]
    test = df[df["ts"] >= VAL_END]

    model = CatBoostClassifier()
    model.load_model(str(model_path))
    if list(model.feature_names_) != ALL_FEATURES:
        raise SystemExit(
            f"[{track}] схема признаков {model_path} не совпадает с витриной: "
            f"модель={model.feature_names_!r} витрина={ALL_FEATURES!r}"
        )

    print(f"[{track}] scoring val={len(val)} test={len(test)} rows with deployed model...")
    scores_val = model.predict_proba(val[ALL_FEATURES])[:, 1]
    scores_test = model.predict_proba(test[ALL_FEATURES])[:, 1]

    scored = pd.concat(
        [
            val[["channel_id", "ts", "y_true"]].assign(score=scores_val, split="val"),
            test[["channel_id", "ts", "y_true"]].assign(score=scores_test, split="test"),
        ],
        ignore_index=True,
    )
    scored.to_parquet(out_path)
    print(f"[{track}] {len(scored)} rows -> {out_path}")


if __name__ == "__main__":
    main()
