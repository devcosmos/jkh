"""Калибровочная кривая (reliability diagram) на test-сплите: когда модель говорит «X%
вероятность отказа», действительно ли отказ случается в ~X% случаев. Отдельная проверка
качества модели, не подменяет ROC-AUC/PR-AUC — та измеряет ранжирование, эта — доверие к
самому числу вероятности, которое видит диспетчер в UI.

Бины фиксированной ширины 0.1 (0-10%, 10-20%, ... 90-100%) — интерпретируется как «модель
говорит X%», а не квантили, которые сместили бы бины под распределение выборки. Бины с
малым числом наблюдений (n < MIN_BIN_SIZE) помечены, а не скрыты — честнее, чем удалить
шумную точку молча.

Запуск: source .venv/bin/activate && python3 ml/evaluation/compute_calibration.py
"""
import json
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"

TRACKS = ["насос_вентилятор", "дым_газ"]
N_BINS = 10
MIN_BIN_SIZE = 30


def compute_for_track(track: str) -> list[dict]:
    con = duckdb.connect()
    df = con.execute(
        f"SELECT score, y_true FROM read_parquet('{ARTIFACTS_DIR / f'scored_{track}.parquet'}') WHERE split = 'test'"
    ).df()

    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    bin_idx = np.clip(np.digitize(df["score"], edges[1:-1]), 0, N_BINS - 1)

    bins = []
    for i in range(N_BINS):
        mask = bin_idx == i
        n = int(mask.sum())
        bins.append(
            {
                "bin_start": round(float(edges[i]), 2),
                "bin_end": round(float(edges[i + 1]), 2),
                "n": n,
                "mean_predicted": round(float(df.loc[mask, "score"].mean()), 4) if n else None,
                "observed_rate": round(float(df.loc[mask, "y_true"].mean()), 4) if n else None,
                "reliable": n >= MIN_BIN_SIZE,
            }
        )
    return bins


def main() -> None:
    for track in TRACKS:
        print(f"[{track}] computing calibration on test split...")
        bins = compute_for_track(track)
        out_path = ARTIFACTS_DIR / f"calibration_{track}.json"
        out_path.write_text(json.dumps(bins, ensure_ascii=False, indent=2))
        print(f"[{track}] -> {out_path}")
        for b in bins:
            if b["n"]:
                print(
                    f"  [{b['bin_start']:.1f}-{b['bin_end']:.1f}) n={b['n']:>8} "
                    f"predicted={b['mean_predicted']:.3f} observed={b['observed_rate']:.3f}"
                    f"{'' if b['reliable'] else '  (мало наблюдений)'}"
                )


if __name__ == "__main__":
    main()
