"""Эпизодная оценка для дыма/газа (аналог scripts/evaluate_episodes.py), на выходе
scripts/train_model_дым_газ.py.

Запуск: source .venv/bin/activate && python3 scripts/evaluate_episodes_дым_газ.py
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "artifacts"
SCORED_PARQUET = ANALYSIS_DIR / "scored_дым_газ.parquet"
EPISODES_PARQUET = ANALYSIS_DIR / "episodes_дым_газ_2024_2026.parquet"
OUT_REPORT = ANALYSIS_DIR / "episode_evaluation_дым_газ.json"

THRESHOLDS = [round(x, 2) for x in [0.05 + 0.02 * i for i in range(28)]]


def build_alert_runs(scored_sorted: pd.DataFrame, threshold: float) -> pd.DataFrame:
    df = scored_sorted
    df["alert"] = df["score"].values >= threshold
    df["run_change"] = (df["alert"] != df.groupby("channel_id")["alert"].shift()).astype(int)
    df["run_id"] = df.groupby("channel_id")["run_change"].cumsum()
    runs = (
        df[df["alert"]]
        .groupby(["channel_id", "run_id"])
        .agg(run_start=("ts", "min"), run_end=("ts", "max"))
        .reset_index()
    )
    return runs


def evaluate(scored_split_sorted: pd.DataFrame, episodes: pd.DataFrame, threshold: float) -> dict:
    runs = build_alert_runs(scored_split_sorted, threshold)
    n_channels = scored_split_sorted["channel_id"].nunique()
    n_days = (scored_split_sorted["ts"].max() - scored_split_sorted["ts"].min()).total_seconds() / 86400

    detected = 0
    lead_times = []
    matched_run_keys = set()
    for _, ep in episodes.iterrows():
        ep_runs = runs[
            (runs["channel_id"] == ep["channel_id"])
            & (runs["run_start"] < ep["start_time"])
            & (runs["run_start"] >= ep["start_time"] - pd.Timedelta(hours=24))
        ]
        if len(ep_runs):
            detected += 1
            first_run = ep_runs.loc[ep_runs["run_start"].idxmin()]
            lead_times.append((ep["start_time"] - first_run["run_start"]).total_seconds() / 3600)
            for _, r in ep_runs.iterrows():
                matched_run_keys.add((r["channel_id"], r["run_id"]))

    total_runs = len(runs)
    false_runs = total_runs - len(matched_run_keys)
    fp_per_100_devices_per_day = (false_runs / max(n_channels, 1) / max(n_days, 1)) * 100

    return {
        "threshold": threshold,
        "n_true_episodes": len(episodes),
        "n_detected_episodes": detected,
        "episode_recall": detected / len(episodes) if len(episodes) else None,
        "n_alert_runs_total": total_runs,
        "n_false_alert_runs": false_runs,
        "fp_per_100_devices_per_day": fp_per_100_devices_per_day,
        "median_lead_time_hours": float(pd.Series(lead_times).median()) if lead_times else None,
        "mean_lead_time_hours": float(pd.Series(lead_times).mean()) if lead_times else None,
    }


def main() -> None:
    con = duckdb.connect()
    scored = con.execute(f"SELECT * FROM read_parquet('{SCORED_PARQUET}')").fetchdf()
    episodes_all = con.execute(
        f"""
        SELECT ид_канала_данных AS channel_id, start_time
        FROM read_parquet('{EPISODES_PARQUET}')
        WHERE NOT is_flapping_incident
          AND (recovered_at IS NULL
               OR date_diff('second', start_time, recovered_at) >= 3600)
        """
    ).fetchdf()

    results = {"val": [], "test": []}
    for split in ["val", "test"]:
        scored_split = scored[scored["split"] == split].sort_values(["channel_id", "ts"]).reset_index(drop=True)
        lo, hi = scored_split["ts"].min(), scored_split["ts"].max()
        episodes_split = episodes_all[
            (episodes_all["start_time"] >= lo) & (episodes_all["start_time"] <= hi)
        ]
        for thr in THRESHOLDS:
            res = evaluate(scored_split, episodes_split, thr)
            results[split].append(res)
            print(split, res)

    OUT_REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"saved to {OUT_REPORT}")


if __name__ == "__main__":
    main()
