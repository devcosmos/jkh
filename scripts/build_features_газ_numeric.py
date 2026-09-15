"""Добавляет к существующей витрине газовых каналов (подмножество
scripts/build_features_дым_газ.py) признаки на основе СЫРЫХ ЧИСЛОВЫХ показаний концентрации
газа, которые сейчас в состоянийном пайплайне полностью игнорируются: 99,7% событий газовых
каналов — это числовые значения (TRY_CAST(значение_датчика AS DOUBLE) IS NOT NULL), а не
категориальные состояния из STATE_VALUES, и используется только 0,3% сигнала.

Гипотеза: динамика самой концентрации (тренд, отклонение от собственной 7-дневной базовой
линии) несёт информацию о надвигающемся отказе датчика, которой нет в счётчиках
переходов/тревог по состоянию.

Запуск: source .venv/bin/activate && python3 scripts/build_features_газ_numeric.py
Зависит от: docs/analysis/features_дым_газ_2024_2026.parquet (scripts/build_features_дым_газ.py)
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "dataset"
ANALYSIS_DIR = ROOT / "docs" / "analysis"

YEARS = ["2024", "2025", "2026"]
BASE_FEATURES_PARQUET = ANALYSIS_DIR / "features_дым_газ_2024_2026.parquet"
OUT_PARQUET = ANALYSIS_DIR / "features_газ_numeric_2024_2026.parquet"

EVENT_COLUMN_TYPES = {
    "ид_события": "VARCHAR",
    "ид_канала_данных": "VARCHAR",
    "дата": "VARCHAR",
    "время": "VARCHAR",
    "тревожное": "VARCHAR",
    "значение_датчика": "VARCHAR",
}


def main() -> None:
    con = duckdb.connect()
    channels_path = DATASET_DIR / "справочник_каналов_датчиков.csv"
    con.execute(
        f"""
        CREATE VIEW channels AS
        SELECT * FROM read_csv_auto('{channels_path}', header=true)
        """
    )

    union_parts = []
    for year in YEARS:
        path = DATASET_DIR / f"ext-journal-{year}.csv"
        if not path.exists():
            print(f"skip {year}: file not found", file=sys.stderr)
            continue
        print(f"scanning {year}...", file=sys.stderr)
        con.execute(
            f"""
            CREATE OR REPLACE VIEW raw_{year} AS
            SELECT * FROM read_csv('{path}', header=true, types={EVENT_COLUMN_TYPES!r})
            """
        )
        union_parts.append(
            f"""
            SELECT
                TRY_CAST(ид_канала_данных AS BIGINT) AS channel_id,
                CAST(дата || ' ' || время AS TIMESTAMP) AS event_time,
                TRY_CAST(значение_датчика AS DOUBLE) AS value
            FROM raw_{year}
            WHERE ид_события != 'ид_события'
              AND TRY_CAST(значение_датчика AS DOUBLE) IS NOT NULL
              AND TRY_CAST(ид_канала_данных AS BIGINT) IN (
                  SELECT ид_канала_данных FROM channels WHERE тип_датчика = 'Газовый датчик'
              )
            """
        )
    con.execute(f"CREATE OR REPLACE VIEW numeric_events AS {' UNION ALL '.join(union_parts)}")

    print("computing rolling stats per numeric reading (RANGE window frames)...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE numeric_rolling AS
        SELECT
            channel_id, event_time, value AS current_value,
            avg(value) OVER w1h AS avg_ppm_1h,
            max(value) OVER w1h AS max_ppm_1h,
            avg(value) OVER w24h AS avg_ppm_24h,
            max(value) OVER w24h AS max_ppm_24h,
            avg(value) OVER w7d AS avg_ppm_7d,
            max(value) OVER w7d AS max_ppm_7d,
            stddev_pop(value) OVER w7d AS std_ppm_7d
        FROM numeric_events
        WINDOW
            w1h AS (PARTITION BY channel_id ORDER BY event_time
                     RANGE BETWEEN INTERVAL 1 HOUR PRECEDING AND CURRENT ROW),
            w24h AS (PARTITION BY channel_id ORDER BY event_time
                      RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND CURRENT ROW),
            w7d AS (PARTITION BY channel_id ORDER BY event_time
                     RANGE BETWEEN INTERVAL 7 DAY PRECEDING AND CURRENT ROW)
        """
    )

    print("loading base gas grid (from features_дым_газ_2024_2026.parquet)...", file=sys.stderr)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE base_grid AS
        SELECT * FROM read_parquet('{BASE_FEATURES_PARQUET}')
        WHERE тип_датчика = 'Газовый датчик'
        """
    )

    print("asof-joining numeric rolling stats onto the hourly grid...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE joined AS
        SELECT
            g.*,
            n.current_value,
            n.avg_ppm_1h, n.max_ppm_1h,
            n.avg_ppm_24h, n.max_ppm_24h,
            n.avg_ppm_7d, n.max_ppm_7d, n.std_ppm_7d,
            date_diff('second', n.event_time, g.ts) AS seconds_since_last_numeric,
            CASE WHEN n.std_ppm_7d > 0
                 THEN (n.current_value - n.avg_ppm_7d) / n.std_ppm_7d
                 ELSE 0 END AS zscore_7d
        FROM base_grid g
        ASOF LEFT JOIN numeric_rolling n
            ON g.channel_id = n.channel_id AND g.ts >= n.event_time
        """
    )

    con.execute(f"COPY joined TO '{OUT_PARQUET}' (FORMAT PARQUET)")

    n_total = con.execute("SELECT count(*) FROM joined").fetchone()[0]
    n_with_numeric = con.execute("SELECT count(*) FROM joined WHERE current_value IS NOT NULL").fetchone()[0]
    n_pos = con.execute("SELECT count(*) FROM joined WHERE y_true").fetchone()[0]
    print(f"total rows: {n_total}, with numeric telemetry: {n_with_numeric} "
          f"({100*n_with_numeric/n_total:.1f}%), positive: {n_pos} ({100*n_pos/n_total:.3f}%)")
    print(f"saved to {OUT_PARQUET}")


if __name__ == "__main__":
    main()
