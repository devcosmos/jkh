"""Обучает независимый сигнал аномальности (IsolationForest) как дополнение к CatBoost.

Мотивация: CatBoost — обучен на размеченных отказах, поэтому находит только уже виденные
паттерны (раздел «Открытые вопросы»: разметка по состоянию датчика, не по факту поломки —
см. docs/documentation/label-policy.md). IsolationForest — без учителя, на тех же поведенческих
признаках (частоты событий/тревог/переходов, время с последнего события, доля соседей в
отказе), поэтому может заметить необычное поведение канала, не похожее ни на один из
известных сценариев отказа — независимая проверка вместо второго мнения той же модели.

Обучается только на train-сплите (тот же протокол, что и train_model*.py — раздел 6.1
рабочего ТЗ, разрыв 24ч на границах), только на числовых признаках: IsolationForest не
работает с категориальными напрямую, а "тип_датчика"/"current_state" и так учтены в
CatBoost — здесь важен именно паттерн поведения, а не тип устройства.

Запуск: source .venv/bin/activate && python3 scripts/train_anomaly_model.py
"""
import json
from pathlib import Path

import duckdb
import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "artifacts"

TRAIN_END = pd.Timestamp("2025-01-01")
GAP = pd.Timedelta(hours=24)

NUM_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]

TRACKS = ["насос_вентилятор", "дым_газ"]
CONTAMINATION = 0.02  # ожидаемая доля аномалий — согласовано с редкостью реальных отказов


def load_train_split(track: str) -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(
        f"SELECT * FROM read_parquet('{ANALYSIS_DIR / f'features_{track}_2024_2026.parquet'}')"
    ).fetchdf()
    df = df.dropna(subset=["current_state"]).copy()
    df["frac_neighbors_in_fault"] = df["n_neighbors_in_fault"] / df["n_neighbors_total"].clip(lower=1)
    return df[df["ts"] <= TRAIN_END - GAP]


def main() -> None:
    report = {}
    for track in TRACKS:
        print(f"[{track}] loading train split...")
        train = load_train_split(track)
        X = train[NUM_FEATURES].astype(float).values
        print(f"[{track}] fitting IsolationForest on {len(X)} rows...")

        model = IsolationForest(
            n_estimators=200,
            contamination=CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X)

        scores = model.decision_function(X)
        out_path = ANALYSIS_DIR / f"isolation_forest_{track}.joblib"
        joblib.dump({"model": model, "features": NUM_FEATURES}, out_path)

        report[track] = {
            "n_train_rows": len(X),
            "contamination": CONTAMINATION,
            "score_percentiles": {
                "p01": float(pd.Series(scores).quantile(0.01)),
                "p50": float(pd.Series(scores).quantile(0.50)),
                "p99": float(pd.Series(scores).quantile(0.99)),
            },
            "artifact_path": str(out_path.relative_to(ROOT)),
        }
        print(f"[{track}] saved -> {out_path}")

    (ANALYSIS_DIR / "anomaly_model_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("report -> artifacts/anomaly_model_report.json")


if __name__ == "__main__":
    main()
