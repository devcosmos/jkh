"""Строит эпизоды отказа (run-length по значению_датчика) для выбранных типов датчиков
и помечает эпизоды внутри дней аномального флаппинга (много переходов в «Неисправен»
на один канал за сутки — технический инцидент, а не отказ) как известный инцидент,
исключая их из «чистого» набора.

Запуск: source .venv/bin/activate && python3 ml/features/build_episodes.py
"""
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "dataset"
OUT_DIR = ROOT / "artifacts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_VALUES = ["Норма", "Неопределен", "Неисправен", "Обесточен"]
EVENT_COLUMN_TYPES = {
    "ид_события": "VARCHAR",
    "ид_канала_данных": "VARCHAR",
    "дата": "VARCHAR",
    "время": "VARCHAR",
    "тревожное": "VARCHAR",
    "значение_датчика": "VARCHAR",
}

# Канал, дающий больше этого числа переходов в "Неисправен" за один календарный день,
# считается флаппингом/техническим инцидентом (см. docs/documentation/data-audit.md, разделы 6.4-6.5),
# а не независимыми отказами.
FLAP_THRESHOLD_PER_DAY = 10

RUN_SPECS = [
    {
        "name": "насос_вентилятор",
        "years": ["2024", "2025", "2026"],
        "types": ["Состояние насоса", "Состояние вентилятора"],
    },
    {
        "name": "дым_газ",
        "years": ["2024", "2025", "2026"],
        "types": ["Датчик дыма", "Газовый датчик"],
    },
]


def build_episodes(con: duckdb.DuckDBPyConnection, years: list[str], types: list[str]) -> None:
    type_list_sql = ", ".join(f"'{t}'" for t in types)
    state_list_sql = ", ".join(f"'{s}'" for s in STATE_VALUES)

    union_parts = []
    for year in years:
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
                TRY_CAST(ид_канала_данных AS BIGINT) AS ид_канала_данных,
                CAST(дата || ' ' || время AS TIMESTAMP) AS event_time,
                значение_датчика AS state
            FROM raw_{year}
            WHERE ид_события != 'ид_события'
              AND значение_датчика IN ({state_list_sql})
              AND TRY_CAST(ид_канала_данных AS BIGINT) IN (
                  SELECT ид_канала_данных FROM channels WHERE тип_датчика IN ({type_list_sql})
              )
            """
        )

    events_sql = " UNION ALL ".join(union_parts)
    con.execute(f"CREATE OR REPLACE VIEW events_filtered AS {events_sql}")

    print("building runs and episodes...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE VIEW ordered AS
        SELECT *,
            LAG(state) OVER (PARTITION BY ид_канала_данных ORDER BY event_time) AS prev_state
        FROM events_filtered
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW runs AS
        SELECT *,
            SUM(CASE WHEN state IS DISTINCT FROM prev_state THEN 1 ELSE 0 END)
                OVER (PARTITION BY ид_канала_данных ORDER BY event_time
                      ROWS UNBOUNDED PRECEDING) AS run_id
        FROM ordered
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW run_agg AS
        SELECT ид_канала_данных, run_id, state,
               min(event_time) AS start_time,
               max(event_time) AS end_time_last_seen,
               count(*) AS n_records
        FROM runs
        GROUP BY ид_канала_данных, run_id, state
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW run_with_next AS
        SELECT *,
            LEAD(start_time) OVER (PARTITION BY ид_канала_данных ORDER BY run_id) AS next_run_start,
            LEAD(state) OVER (PARTITION BY ид_канала_данных ORDER BY run_id) AS next_state,
            row_number() OVER (PARTITION BY ид_канала_данных ORDER BY run_id) AS run_seq
        FROM run_agg
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW episode_day_counts AS
        SELECT ид_канала_данных, date_trunc('day', start_time) AS day,
               count(*) AS n_episode_starts_that_day
        FROM run_with_next
        WHERE state = 'Неисправен'
        GROUP BY 1, 2
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW episodes AS
        SELECT
            r.ид_канала_данных,
            c.тип_датчика,
            c.тег_инженерной_системы,
            c.название_датчика,
            r.start_time,
            r.end_time_last_seen,
            r.next_run_start AS recovered_at,
            r.next_state AS recovered_to_state,
            r.n_records,
            (r.run_seq = 1) AS left_censored,
            (r.next_run_start IS NULL) AS right_censored,
            (d.n_episode_starts_that_day > {FLAP_THRESHOLD_PER_DAY}) AS is_flapping_incident,
            d.n_episode_starts_that_day
        FROM run_with_next r
        JOIN channels c ON c.ид_канала_данных = r.ид_канала_данных
        JOIN episode_day_counts d
            ON d.ид_канала_данных = r.ид_канала_данных
           AND d.day = date_trunc('day', r.start_time)
        WHERE r.state = 'Неисправен'
        """
    )


def main() -> None:
    con = duckdb.connect()
    channels_path = DATASET_DIR / "справочник_каналов_датчиков.csv"
    con.execute(
        f"CREATE VIEW channels AS SELECT * FROM read_csv_auto('{channels_path}', header=true)"
    )

    all_summaries = {}
    for spec in RUN_SPECS:
        name, years, types = spec["name"], spec["years"], spec["types"]
        print(f"=== {name} ({years}) ===", file=sys.stderr)
        build_episodes(con, years, types)

        out_parquet = OUT_DIR / f"episodes_{name}_{years[0]}_{years[-1]}.parquet"
        con.execute(f"COPY episodes TO '{out_parquet}' (FORMAT PARQUET)")

        total_episodes = con.execute("SELECT count(*) FROM episodes").fetchone()[0]
        n_flapping = con.execute(
            "SELECT count(*) FROM episodes WHERE is_flapping_incident"
        ).fetchone()[0]

        by_type = con.execute(
            """
            SELECT тип_датчика,
                   count(*) AS n_episodes_total,
                   sum(CASE WHEN NOT is_flapping_incident THEN 1 ELSE 0 END) AS n_episodes_clean,
                   sum(CASE WHEN is_flapping_incident THEN 1 ELSE 0 END) AS n_episodes_flapping,
                   count(DISTINCT ид_канала_данных) AS n_channels_total,
                   count(DISTINCT CASE WHEN NOT is_flapping_incident THEN ид_канала_данных END)
                       AS n_channels_clean,
                   sum(CASE WHEN left_censored THEN 1 ELSE 0 END) AS n_left_censored,
                   sum(CASE WHEN right_censored THEN 1 ELSE 0 END) AS n_right_censored,
                   median(CASE WHEN NOT is_flapping_incident
                          THEN date_diff('second', start_time, recovered_at) END)
                       AS median_duration_sec_clean
            FROM episodes
            GROUP BY тип_датчика
            """
        ).fetchall()
        cols = [d[0] for d in con.description]

        summary = {
            "years": years,
            "target_types": types,
            "flap_threshold_per_day": FLAP_THRESHOLD_PER_DAY,
            "total_episodes": total_episodes,
            "n_flagged_as_flapping_incident": n_flapping,
            "by_type": [dict(zip(cols, row)) for row in by_type],
            "output_parquet": str(out_parquet.relative_to(ROOT)),
        }
        out_summary = OUT_DIR / f"episodes_{name}_{years[0]}_{years[-1]}_summary.json"
        out_summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        all_summaries[name] = summary
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

    print(json.dumps(all_summaries, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
