"""Готовит компактный файл-«поток» событий для worker'а живого инференса: только
насос/вентилятор, только с начала test-периода (2025-07-01) — не весь датасет (16 ГБ),
а ровно то, что нужно для демонстрации сценария replay + live inference.

Запуск: source .venv/bin/activate && python3 scripts/build_replay_feed.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "dataset"
OUT_PATH = ROOT / "docs" / "analysis" / "replay_feed_насос_вентилятор.parquet"

REPLAY_START = "2025-07-01"  # начало test-периода в train_model.py — честно "невиданные" данные
TYPES = ["Состояние насоса", "Состояние вентилятора"]
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
    type_list_sql = ", ".join(f"'{t}'" for t in TYPES)
    con.execute(
        f"CREATE VIEW channels AS SELECT * FROM read_csv_auto('{DATASET_DIR / 'справочник_каналов_датчиков.csv'}', header=true)"
    )

    parts = []
    for year in ["2025", "2026"]:
        path = DATASET_DIR / f"ext-journal-{year}.csv"
        con.execute(
            f"CREATE OR REPLACE VIEW raw_{year} AS SELECT * FROM read_csv('{path}', header=true, types={EVENT_COLUMN_TYPES!r})"
        )
        parts.append(
            f"""
            SELECT TRY_CAST(ид_канала_данных AS BIGINT) AS channel_id,
                   CAST(дата || ' ' || время AS TIMESTAMP) AS event_time,
                   значение_датчика AS state,
                   (lower(тревожное) = 'true') AS is_alarm
            FROM raw_{year}
            WHERE ид_события != 'ид_события'
              AND значение_датчика IN ('Норма', 'Неопределен', 'Неисправен', 'Обесточен')
              AND CAST(дата || ' ' || время AS TIMESTAMP) >= TIMESTAMP '{REPLAY_START}'
              AND TRY_CAST(ид_канала_данных AS BIGINT) IN (
                  SELECT ид_канала_данных FROM channels WHERE тип_датчика IN ({type_list_sql})
              )
            """
        )
    con.execute(f"CREATE VIEW feed AS {' UNION ALL '.join(parts)}")
    con.execute(f"COPY (SELECT * FROM feed ORDER BY event_time) TO '{OUT_PATH}' (FORMAT PARQUET)")

    n, lo, hi = con.execute("SELECT count(*), min(event_time), max(event_time) FROM feed").fetchone()
    print(f"{n} rows, {lo} .. {hi} -> {OUT_PATH}")


if __name__ == "__main__":
    main()
