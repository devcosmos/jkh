"""Строит витрину признаков на часовой сетке для «Отказ датчика» (насос, вентилятор)
согласно docs/documentation/label-policy.md: окна 1ч/24ч/7сут, цель y(t) = новый очищенный эпизод
в (t, t+24ч]. Текущая неисправность на момент t исключается из обучающей популяции.

Запуск: source .venv/bin/activate && python3 scripts/build_features.py
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "dataset"
ANALYSIS_DIR = ROOT / "docs" / "documentation" / "analysis"

YEARS = ["2024", "2025", "2026"]
TARGET_TYPES = ["Состояние насоса", "Состояние вентилятора"]
STATE_VALUES = ["Норма", "Неопределен", "Неисправен", "Обесточен"]
EPISODES_PARQUET = ANALYSIS_DIR / "episodes_насос_вентилятор_2024_2026.parquet"
OUT_PARQUET = ANALYSIS_DIR / "features_насос_вентилятор_2024_2026.parquet"

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
        SELECT *, regexp_replace(тег_инженерной_системы, '\\d+\\.$', '') AS location_group
        FROM read_csv_auto('{channels_path}', header=true)
        """
    )

    type_list_sql = ", ".join(f"'{t}'" for t in TARGET_TYPES)
    state_list_sql = ", ".join(f"'{s}'" for s in STATE_VALUES)

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
                значение_датчика AS state,
                (lower(тревожное) = 'true') AS is_alarm
            FROM raw_{year}
            WHERE ид_события != 'ид_события'
              AND значение_датчика IN ({state_list_sql})
              AND TRY_CAST(ид_канала_данных AS BIGINT) IN (
                  SELECT ид_канала_данных FROM channels WHERE тип_датчика IN ({type_list_sql})
              )
            """
        )
    con.execute(f"CREATE OR REPLACE VIEW events_raw AS {' UNION ALL '.join(union_parts)}")

    print("computing per-event cumulative counters...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE events_with_prev AS
        SELECT channel_id, event_time, state, is_alarm,
               LAG(state) OVER (PARTITION BY channel_id ORDER BY event_time) AS prev_state
        FROM events_raw
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE events_cum AS
        SELECT
            channel_id, event_time, state, is_alarm,
            row_number() OVER w AS cum_events,
            sum(CASE WHEN is_alarm THEN 1 ELSE 0 END) OVER w AS cum_alarms,
            sum(CASE WHEN state IS DISTINCT FROM prev_state THEN 1 ELSE 0 END) OVER w
                AS cum_transitions
        FROM events_with_prev
        WINDOW w AS (PARTITION BY channel_id ORDER BY event_time
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        """
    )

    print("loading clean episodes...", file=sys.stderr)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE episodes_clean AS
        SELECT
            ид_канала_данных AS channel_id,
            start_time,
            COALESCE(recovered_at, TIMESTAMP '9999-12-31') AS end_time_open
        FROM read_parquet('{EPISODES_PARQUET}')
        WHERE NOT is_flapping_incident
          AND (recovered_at IS NULL
               OR date_diff('second', start_time, recovered_at) >= 3600)
        """
    )

    print("building hourly grid...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE channel_bounds AS
        SELECT channel_id,
               date_trunc('hour', min(event_time)) + INTERVAL 7 DAY AS grid_start,
               date_trunc('hour', max(event_time)) AS grid_end,
               max(event_time) AS channel_max_time
        FROM events_raw
        GROUP BY channel_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE grid AS
        SELECT channel_id, channel_max_time,
               unnest(generate_series(grid_start, grid_end, INTERVAL 1 HOUR)) AS t
        FROM channel_bounds
        """
    )

    print("asof joins for windowed counters and current state...", file=sys.stderr)
    for w_name, w_sql in [("1h", "INTERVAL 1 HOUR"), ("24h", "INTERVAL 24 HOUR"), ("7d", "INTERVAL 7 DAY")]:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE cum_at_t_minus_{w_name} AS
            SELECT g.channel_id, g.t,
                   COALESCE(e.cum_alarms, 0) AS cum_alarms,
                   COALESCE(e.cum_transitions, 0) AS cum_transitions,
                   COALESCE(e.cum_events, 0) AS cum_events
            FROM grid g
            ASOF LEFT JOIN events_cum e
                ON g.channel_id = e.channel_id AND (g.t - {w_sql}) >= e.event_time
            """
        )

    con.execute(
        """
        CREATE OR REPLACE TABLE cum_at_t AS
        SELECT g.channel_id, g.t, c.location_group,
               COALESCE(e.cum_alarms, 0) AS cum_alarms,
               COALESCE(e.cum_transitions, 0) AS cum_transitions,
               COALESCE(e.cum_events, 0) AS cum_events,
               e.state AS current_state,
               e.event_time AS last_event_time
        FROM grid g
        JOIN channels c ON c.ид_канала_данных = g.channel_id
        ASOF LEFT JOIN events_cum e
            ON g.channel_id = e.channel_id AND g.t >= e.event_time
        """
    )

    print("computing neighbor-in-fault counts (same location_group)...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE neighbor_agg AS
        SELECT channel_id, t,
               sum(CASE WHEN current_state = 'Неисправен' THEN 1 ELSE 0 END)
                   OVER (PARTITION BY t, location_group)
               - (CASE WHEN current_state = 'Неисправен' THEN 1 ELSE 0 END) AS n_neighbors_in_fault,
               count(*) OVER (PARTITION BY t, location_group) - 1 AS n_neighbors_total
        FROM cum_at_t
        """
    )

    print("computing labels from clean episodes (asof forward/backward)...", file=sys.stderr)
    con.execute(
        """
        CREATE OR REPLACE TABLE next_episode AS
        SELECT g.channel_id, g.t, ep.start_time AS next_start
        FROM grid g
        ASOF LEFT JOIN episodes_clean ep
            ON g.channel_id = ep.channel_id AND g.t < ep.start_time
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE prev_episode AS
        SELECT g.channel_id, g.t, ep.start_time AS prev_start, ep.end_time_open AS prev_end
        FROM grid g
        ASOF LEFT JOIN episodes_clean ep
            ON g.channel_id = ep.channel_id AND g.t >= ep.start_time
        """
    )

    print("assembling final feature table...", file=sys.stderr)
    con.execute(
        f"""
        CREATE OR REPLACE VIEW features AS
        SELECT
            g.channel_id,
            c.тип_датчика,
            g.t AS ts,
            (t0.cum_alarms - m1h.cum_alarms) AS n_alarms_1h,
            (t0.cum_alarms - m24h.cum_alarms) AS n_alarms_24h,
            (t0.cum_alarms - m7d.cum_alarms) AS n_alarms_7d,
            (t0.cum_transitions - m1h.cum_transitions) AS n_transitions_1h,
            (t0.cum_transitions - m24h.cum_transitions) AS n_transitions_24h,
            (t0.cum_transitions - m7d.cum_transitions) AS n_transitions_7d,
            (t0.cum_events - m1h.cum_events) AS n_events_1h,
            (t0.cum_events - m24h.cum_events) AS n_events_24h,
            (t0.cum_events - m7d.cum_events) AS n_events_7d,
            t0.current_state,
            date_diff('second', t0.last_event_time, g.t) AS seconds_since_last_event,
            na.n_neighbors_in_fault,
            na.n_neighbors_total,
            (pe.prev_start IS NOT NULL AND g.t < pe.prev_end) AS in_fault_now,
            (ne.next_start IS NOT NULL AND ne.next_start <= g.t + INTERVAL 24 HOUR) AS y_true,
            (g.t + INTERVAL 24 HOUR <= g.channel_max_time) AS future_fully_observed
        FROM grid g
        JOIN channels c ON c.ид_канала_данных = g.channel_id
        JOIN cum_at_t t0 ON t0.channel_id = g.channel_id AND t0.t = g.t
        JOIN cum_at_t_minus_1h m1h ON m1h.channel_id = g.channel_id AND m1h.t = g.t
        JOIN cum_at_t_minus_24h m24h ON m24h.channel_id = g.channel_id AND m24h.t = g.t
        JOIN cum_at_t_minus_7d m7d ON m7d.channel_id = g.channel_id AND m7d.t = g.t
        JOIN next_episode ne ON ne.channel_id = g.channel_id AND ne.t = g.t
        JOIN prev_episode pe ON pe.channel_id = g.channel_id AND pe.t = g.t
        JOIN neighbor_agg na ON na.channel_id = g.channel_id AND na.t = g.t
        WHERE NOT (pe.prev_start IS NOT NULL AND g.t < pe.prev_end)
          AND (y_true OR future_fully_observed)
        """
    )

    con.execute(f"COPY features TO '{OUT_PARQUET}' (FORMAT PARQUET)")

    n_total = con.execute("SELECT count(*) FROM features").fetchone()[0]
    n_pos = con.execute("SELECT count(*) FROM features WHERE y_true").fetchone()[0]
    by_type = con.execute(
        "SELECT тип_датчика, count(*), sum(CASE WHEN y_true THEN 1 ELSE 0 END) FROM features GROUP BY 1"
    ).fetchall()
    print(f"total rows: {n_total}, positive: {n_pos} ({100*n_pos/n_total:.3f}%)")
    for row in by_type:
        print(row)
    print(f"saved to {OUT_PARQUET}")


if __name__ == "__main__":
    main()
