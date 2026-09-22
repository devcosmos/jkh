"""Разовый генератор маленьких детерминированных фикстур для
backend/tests/test_offline_runtime_parity.py (ML-06 в analys_and_todo.md) — не часть тестового
прогона, запускается вручную при необходимости обновить фикстуры из свежих артефактов.

CI не имеет доступа к artifacts/features_*.parquet (регенерируемые обучающие артефакты,
исключены из Git политикой хранения — см. корневой .gitignore, файлы по 90-670 МБ). Полноценная
проверка offline/runtime на реальных данных возможна только локально (см.
scripts/maintenance/check_worker_feature_parity.py). Этот скрипт вырезает маленький
детерминированный срез из настоящих committed-в-момент-генерации артефактов — координаты
(канал, момент) выбраны не случайно, а зафиксированы здесь, чтобы CI имел неслучайный,
воспроизводимый контракт-тест на реальных числах, без веса полных артефактов.

Запуск: source .venv/bin/activate && python3 backend/tests/fixtures/parity/generate_fixtures.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = ROOT / "artifacts"
OUT_DIR = Path(__file__).resolve().parent

TRACKS = ["насос_вентилятор", "дым_газ"]
N_MATURE_CHANNELS = 4
N_COLD_START_CHANNELS = 2


def main() -> None:
    con = duckdb.connect()
    for track in TRACKS:
        feed_path = ARTIFACTS_DIR / f"replay_feed_{track}.parquet"
        features_path = ARTIFACTS_DIR / f"features_{track}_2024_2026.parquet"

        # Каналы с хотя бы одной группой одинаковых event_time (см. Технические_заметки.md,
        # запись «Тай-брейк одинаковых timestamp») — гарантирует, что фикстура покрывает этот
        # случай, а не полагается на случайный выбор.
        dup_channels = con.execute(
            f"""
            SELECT channel_id FROM (
                SELECT channel_id, event_time, count(*) AS n
                FROM read_parquet('{feed_path}')
                GROUP BY channel_id, event_time
            )
            WHERE n > 1
            GROUP BY channel_id
            ORDER BY channel_id
            LIMIT 2
            """
        ).fetchdf()["channel_id"].tolist()

        mature_channels = con.execute(
            f"SELECT DISTINCT channel_id FROM read_parquet('{feed_path}') ORDER BY channel_id LIMIT {N_MATURE_CHANNELS}"
        ).fetchdf()["channel_id"].tolist()

        channels = sorted(set(dup_channels) | set(mature_channels))

        con.execute(
            f"""
            COPY (
                SELECT * FROM read_parquet('{feed_path}')
                WHERE channel_id IN ({','.join(map(str, channels))})
                ORDER BY event_time, event_id
            ) TO '{OUT_DIR / f"feed_{track}.parquet"}' (FORMAT PARQUET)
            """
        )

        # Точки сравнения: детерминированные (первые по порядку, не random()) — «зрелый» режим
        # (>=3 недели с начала фида) и «холодный старт» (первые сутки), плюс каналы с дублями
        # timestamp из dup_channels на «зрелых» точках.
        # Точки, где САМОЕ ПОСЛЕДНЕЕ событие перед ts входит в группу одинакового event_time —
        # иначе тай-брейк по id (current_state) может случайно не сработать ни разу, даже если
        # канал где-то в истории содержит дубли (важно только дубль НА ГРАНИЦЕ окна).
        dup_boundary_points = con.execute(
            f"""
            WITH dup_groups AS (
                SELECT channel_id, event_time, count(*) AS n
                FROM read_parquet('{feed_path}')
                WHERE channel_id IN ({','.join(map(str, channels))})
                GROUP BY channel_id, event_time
                HAVING count(*) > 1
            )
            SELECT DISTINCT f.channel_id, f.ts, 'dup_boundary' AS regime
            FROM dup_groups d
            JOIN read_parquet('{features_path}') f
                ON f.channel_id = d.channel_id
               AND f.ts = date_trunc('hour', d.event_time) + INTERVAL 1 HOUR
            ORDER BY f.channel_id, f.ts
            LIMIT 6
            """
        ).fetchdf()

        # Точки на канал определяются относительно ЕГО СОБСТВЕННОГО диапазона в фиде (не
        # фиксированным календарным окном) — разные каналы стартуют в фиде в разное время.
        points = con.execute(
            f"""
            WITH per_channel_events AS (
                SELECT channel_id,
                       date_trunc('hour', event_time) + INTERVAL 1 HOUR AS ts,
                       min(event_time) OVER (PARTITION BY channel_id) AS channel_start
                FROM read_parquet('{feed_path}')
                WHERE channel_id IN ({','.join(map(str, channels))})
                GROUP BY channel_id, event_time
            ),
            candidates AS (
                SELECT DISTINCT channel_id, ts,
                       CASE WHEN ts >= channel_start + INTERVAL 21 DAY THEN 'mature'
                            WHEN ts < channel_start + INTERVAL 1 DAY THEN 'cold_start'
                       END AS regime
                FROM per_channel_events
            ),
            mature AS (
                SELECT f.channel_id, f.ts, 'mature' AS regime,
                       row_number() OVER (PARTITION BY f.channel_id ORDER BY f.ts) AS rn
                FROM read_parquet('{features_path}') f
                JOIN candidates c ON c.channel_id = f.channel_id AND c.ts = f.ts AND c.regime = 'mature'
            ),
            cold_start AS (
                SELECT f.channel_id, f.ts, 'cold_start' AS regime,
                       row_number() OVER (PARTITION BY f.channel_id ORDER BY f.ts) AS rn
                FROM read_parquet('{features_path}') f
                JOIN candidates c ON c.channel_id = f.channel_id AND c.ts = f.ts AND c.regime = 'cold_start'
                WHERE f.channel_id IN ({','.join(map(str, mature_channels[:N_COLD_START_CHANNELS]))})
            )
            SELECT channel_id, ts, regime FROM mature WHERE rn <= 3
            UNION ALL
            SELECT channel_id, ts, regime FROM cold_start WHERE rn <= 2
            ORDER BY channel_id, ts
            """
        ).fetchdf()
        import pandas as pd

        points = (
            pd.concat([points, dup_boundary_points], ignore_index=True)
            .drop_duplicates(subset=["channel_id", "ts"])
            .sort_values(["channel_id", "ts"])
            .reset_index(drop=True)
        )

        selected = ", ".join(f"({row.channel_id}, TIMESTAMP '{row.ts}')" for row in points.itertuples())
        con.execute(
            f"""
            COPY (
                SELECT f.* FROM read_parquet('{features_path}') f
                JOIN (VALUES {selected}) AS pts(channel_id, ts)
                    ON f.channel_id = pts.channel_id AND f.ts = pts.ts
                ORDER BY f.channel_id, f.ts
            ) TO '{OUT_DIR / f"expected_{track}.parquet"}' (FORMAT PARQUET)
            """
        )
        points["regime"].to_frame().assign(channel_id=points["channel_id"], ts=points["ts"].astype(str)).to_csv(
            OUT_DIR / f"points_{track}.csv", index=False
        )
        print(f"[{track}] {len(channels)} channels, {len(points)} points -> {OUT_DIR}")


if __name__ == "__main__":
    main()
