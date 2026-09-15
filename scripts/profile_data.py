"""Профиль полного объёма событий по годам через DuckDB: число строк, доля тревог,
распределение значений датчика, связность каналов со справочником, типы с "Неисправен".

Запуск: source .venv/bin/activate && python3 scripts/profile_data.py
"""
import json
import sys
from pathlib import Path

import duckdb

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"

YEAR_FILES = {
    str(y): f"ext-journal-{y}.csv" for y in range(2019, 2027)
}
CHANNELS_FILE = "справочник_каналов_датчиков.csv"


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
    channels_path = DATASET_DIR / CHANNELS_FILE
    con.execute(
        f"CREATE VIEW channels AS SELECT * FROM read_csv_auto('{channels_path}', header=true)"
    )

    report = {}
    for year, fname in YEAR_FILES.items():
        path = DATASET_DIR / fname
        if not path.exists():
            print(f"skip {year}: {fname} not found", file=sys.stderr)
            continue
        print(f"profiling {year} ({path.stat().st_size / 1e9:.2f} GB)...", file=sys.stderr)
        # Читаем все столбцы как VARCHAR: годовые файлы содержат встроенные повторные
        # строки заголовка (склейка нескольких экспортов), которые ломают автоопределение типов.
        con.execute(
            f"""
            CREATE OR REPLACE VIEW events_{year}_raw AS
            SELECT * FROM read_csv(
                '{path}', header=true, types={EVENT_COLUMN_TYPES!r}
            )
            """
        )
        embedded_headers = con.execute(
            f"SELECT count(*) FROM events_{year}_raw WHERE ид_события = 'ид_события'"
        ).fetchone()[0]
        con.execute(
            f"""
            CREATE OR REPLACE VIEW events_{year} AS
            SELECT
                TRY_CAST(ид_события AS BIGINT) AS ид_события,
                TRY_CAST(ид_канала_данных AS BIGINT) AS ид_канала_данных,
                дата,
                время,
                lower(тревожное) AS тревожное,
                значение_датчика
            FROM events_{year}_raw
            WHERE ид_события != 'ид_события'
            """
        )

        total_rows = con.execute(f"SELECT count(*) FROM events_{year}").fetchone()[0]
        alarm_true = con.execute(
            f"SELECT count(*) FROM events_{year} WHERE тревожное IN ('true', 't', 'True', 'TRUE')"
        ).fetchone()[0]
        matched = con.execute(
            f"""
            SELECT count(*) FROM events_{year} e
            INNER JOIN channels c ON e.ид_канала_данных = c.ид_канала_данных
            """
        ).fetchone()[0]
        neispraven = con.execute(
            f"""
            SELECT c.тип_датчика, count(*) AS n, count(DISTINCT e.ид_канала_данных) AS n_channels
            FROM events_{year} e
            INNER JOIN channels c ON e.ид_канала_данных = c.ид_канала_данных
            WHERE e.значение_датчика = 'Неисправен'
            GROUP BY c.тип_датчика
            ORDER BY n DESC
            """
        ).fetchall()
        distinct_values = con.execute(
            f"""
            SELECT значение_датчика, count(*) AS n
            FROM events_{year}
            WHERE значение_датчика IN ('Норма', 'Неопределен', 'Неисправен', 'Обесточен')
            GROUP BY значение_датчика
            ORDER BY n DESC
            """
        ).fetchall()
        date_range = con.execute(
            f"SELECT min(дата), max(дата) FROM events_{year}"
        ).fetchone()

        report[year] = {
            "total_rows": total_rows,
            "embedded_duplicate_header_rows": embedded_headers,
            "alarm_true": alarm_true,
            "channels_matched_to_registry": matched,
            "channels_unmatched": total_rows - matched,
            "date_range": [str(date_range[0]), str(date_range[1])],
            "state_value_counts": {k: v for k, v in distinct_values},
            "neispraven_by_type": [{"тип_датчика": t, "n": n, "n_channels": c} for t, n, c in neispraven],
        }

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
