"""Готовит компактные файлы-«потоки» событий для worker'а живого инференса, по одному на
каждый независимо оцениваемый трек (тема 18 CSV с ответами организаторов), только с начала
test-периода (2025-07-01) — не весь датасет (16 ГБ), а ровно то, что нужно для демонстрации
сценария replay + live inference.

Запуск: source .venv/bin/activate && python3 scripts/build_replay_feed.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "dataset"
OUT_DIR = ROOT / "artifacts"

REPLAY_START = "2025-07-01"  # начало test-периода в train_model*.py — честно "невиданные" данные
STATE_VALUES = ["Норма", "Неопределен", "Неисправен", "Обесточен"]  # см. scripts/build_episodes.py
RUN_SPECS = [
    ("насос_вентилятор", ["Состояние насоса", "Состояние вентилятора"]),
    ("дым_газ", ["Датчик дыма", "Газовый датчик"]),
]
EVENT_COLUMN_TYPES = {
    "ид_события": "VARCHAR",
    "ид_канала_данных": "VARCHAR",
    "дата": "VARCHAR",
    "время": "VARCHAR",
    "тревожное": "VARCHAR",
    "значение_датчика": "VARCHAR",
}


def build_feed(con: duckdb.DuckDBPyConnection, name: str, types: list[str]) -> None:
    out_path = OUT_DIR / f"replay_feed_{name}.parquet"
    type_list_sql = ", ".join(f"'{t}'" for t in types)
    state_list_sql = ", ".join(f"'{s}'" for s in STATE_VALUES)

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
                   (lower(тревожное) = 'true') AS is_alarm,
                   TRY_CAST(ид_события AS BIGINT) AS event_id
            FROM raw_{year}
            WHERE ид_события != 'ид_события'
              AND значение_датчика IN ({state_list_sql})
              AND CAST(дата || ' ' || время AS TIMESTAMP) >= TIMESTAMP '{REPLAY_START}'
              AND TRY_CAST(ид_канала_данных AS BIGINT) IN (
                  SELECT ид_канала_данных FROM channels WHERE тип_датчика IN ({type_list_sql})
              )
            """
        )
    con.execute(f"CREATE OR REPLACE VIEW feed AS {' UNION ALL '.join(parts)}")
    # event_id сохраняется в файле как тай-брейк порядка вставки — worker сортирует по
    # (event_time, event_id) перед ingest_tick, так что PK автоинкремента ChannelEvent.id
    # получается в правильном хронологическом порядке даже для событий с одинаковым
    # event_time (секундная точность источника). Без этого при нескольких событиях канала
    # с одинаковым timestamp worker и обучение (build_features.py — тот же тай-брейк) могли
    # по-разному определить current_state и внутрисекундные переходы (найдено
    # scripts/check_worker_feature_parity.py). Дедупликации здесь нет и не должно быть —
    # каждое такое событие обычно настоящий быстрый переход состояния, не дубль записи.
    con.execute(f"COPY (SELECT * FROM feed ORDER BY event_time, event_id) TO '{out_path}' (FORMAT PARQUET)")

    n, lo, hi = con.execute("SELECT count(*), min(event_time), max(event_time) FROM feed").fetchone()
    print(f"[{name}] {n} rows, {lo} .. {hi} -> {out_path}")


def main() -> None:
    con = duckdb.connect()
    con.execute(
        f"CREATE VIEW channels AS SELECT * FROM read_csv_auto('{DATASET_DIR / 'справочник_каналов_датчиков.csv'}', header=true)"
    )
    for name, types in RUN_SPECS:
        build_feed(con, name, types)


if __name__ == "__main__":
    main()
