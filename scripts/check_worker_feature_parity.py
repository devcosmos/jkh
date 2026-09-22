"""Диагностика: совпадают ли признаки, которые видит worker в реальном времени, с признаками
из обучающей витрины (scripts/build_features.py) на одном и том же срезе (канал, момент t).

Не сравнивает соседские признаки (n_neighbors_*) — там расхождение уже подтверждено чтением
кода (train строит витрину только по каналам своего трека, worker берёт всех соседей по
location_group без фильтра по типу датчика) и не нуждается в числовой проверке.

Использует не переигрывание CSV-журналов, а ровно то, чем реально кормится worker —
docs/documentation/analysis/replay_feed_насос_вентилятор.parquet — и обучающую витрину
docs/documentation/analysis/features_насос_вентилятор_2024_2026.parquet как эталон. Точки для
сравнения берутся из уже посчитанной витрины, поэтому число расхождений — не артефакт выбора
случайных моментов, а сопоставление с теми же точками, что видела модель при обучении.

Признаки worker считаются НАСТОЯЩЕЙ функцией backend.app.workers.replay_worker.compute_features_for_channel
против тестового Postgres (jkh_test_db, тот же, что использует pytest) — не переписаны заново,
чтобы не завести отдельный источник расхождений.

Запуск: source .venv/bin/activate && JKH_DATABASE_URL=postgresql+psycopg://jkh:jkh@localhost:55432/jkh_test \
    python3 scripts/check_worker_feature_parity.py
"""
import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("JKH_DATABASE_URL", "postgresql+psycopg://jkh:jkh@localhost:55432/jkh_test")

import duckdb
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import Base  # noqa: E402
from app.models.entities import Channel, ChannelEvent, ChannelRetentionWatermark  # noqa: E402
from app.workers.replay_worker import compute_features_for_channel  # noqa: E402

ANALYSIS_DIR = ROOT / "docs" / "documentation" / "analysis"
FEED_PARQUET = ANALYSIS_DIR / "replay_feed_насос_вентилятор.parquet"
FEATURES_PARQUET = ANALYSIS_DIR / "features_насос_вентилятор_2024_2026.parquet"
RETENTION = dt.timedelta(days=7)

OWN_CHANNEL_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "current_state", "seconds_since_last_event",
]

engine = create_engine(os.environ["JKH_DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def pick_sample_points(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Точки (channel_id, ts) для сравнения — час сразу после реального события канала в
    replay-фиде (гарантирует, что в окне worker'а вообще есть данные), пересечённый с
    обучающей витриной. Отдельно 'зрелый' режим (>=3 недели с начала фида, у worker уже
    накопилось 7 суток) и 'холодный старт' (первые сутки фида, где у worker предыстории почти
    нет, а обучение её видело за счёт полного журнала 2024-2026)."""
    channels = con.execute(
        f"SELECT DISTINCT channel_id FROM read_parquet('{FEED_PARQUET}') ORDER BY channel_id LIMIT 60"
    ).fetchdf()["channel_id"].tolist()

    rows = []
    for cid in channels:
        for regime, lo, hi in [
            ("mature", "2025-08-01", "2026-03-01"),
            ("cold_start", "2025-07-01", "2025-07-02"),
        ]:
            limit = 6 if regime == "mature" else 2
            candidates = con.execute(
                f"""
                SELECT DISTINCT f.channel_id, f.ts
                FROM read_parquet('{FEATURES_PARQUET}') f
                JOIN (
                    SELECT DISTINCT channel_id, date_trunc('hour', event_time) + INTERVAL 1 HOUR AS ts
                    FROM read_parquet('{FEED_PARQUET}')
                    WHERE channel_id = {cid}
                      AND event_time >= TIMESTAMP '{lo}' AND event_time < TIMESTAMP '{hi}'
                ) e ON e.channel_id = f.channel_id AND e.ts = f.ts
                WHERE f.channel_id = {cid}
                ORDER BY random() LIMIT {limit}
                """
            ).fetchdf()
            candidates["regime"] = regime
            rows.append(candidates)
    return pd.concat(rows, ignore_index=True)


def worker_features_at(con: duckdb.DuckDBPyConnection, db, channel_id: int, ts: pd.Timestamp) -> dict | None:
    ts = ts.to_pydatetime().replace(tzinfo=dt.timezone.utc)
    window_start = ts - RETENTION
    events = con.execute(
        f"""
        SELECT channel_id, event_time, state, is_alarm
        FROM read_parquet('{FEED_PARQUET}')
        WHERE channel_id = {channel_id}
          AND event_time > TIMESTAMP '{window_start.replace(tzinfo=None)}'
          AND event_time <= TIMESTAMP '{ts.replace(tzinfo=None)}'
        ORDER BY event_time, event_id
        """
    ).fetchdf()

    db.execute(text("TRUNCATE TABLE channel_events, channel_retention_watermark RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE channels RESTART IDENTITY CASCADE"))
    channel = Channel(external_channel_id=channel_id, sensor_type="Состояние насоса")
    db.add(channel)
    db.flush()

    # Событие, которое prune_old_events реально вытеснил бы к этому моменту — без него
    # проверяется старое (неисправленное) поведение worker'а.
    pruned = con.execute(
        f"""
        SELECT state FROM read_parquet('{FEED_PARQUET}')
        WHERE channel_id = {channel_id} AND event_time <= TIMESTAMP '{window_start.replace(tzinfo=None)}'
        ORDER BY event_time DESC, event_id DESC LIMIT 1
        """
    ).fetchdf()
    if not pruned.empty:
        db.add(
            ChannelRetentionWatermark(
                channel_id=channel.id,
                last_pruned_state=pruned.iloc[0]["state"],
                last_pruned_event_time=window_start,
            )
        )

    if not events.empty:
        db.bulk_insert_mappings(
            ChannelEvent,
            [
                dict(
                    channel_id=channel.id,
                    event_time=row.event_time.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                    state=row.state,
                    is_alarm=bool(row.is_alarm),
                )
                for row in events.itertuples()
            ],
        )
    db.commit()

    return compute_features_for_channel(db, channel, ts, ["Состояние насоса", "Состояние вентилятора"])


def main() -> None:
    Base.metadata.create_all(engine)
    con = duckdb.connect()
    db = SessionLocal()

    points = pick_sample_points(con)
    print(f"comparing {len(points)} (channel, ts) points\n")

    mismatch_counts = {f: 0 for f in OWN_CHANNEL_FEATURES}
    mismatch_examples = {f: [] for f in OWN_CHANNEL_FEATURES}
    n_worker_none = 0
    n_ok = 0
    n_compared = 0

    for row in points.itertuples():
        train_row = con.execute(
            f"""
            SELECT * FROM read_parquet('{FEATURES_PARQUET}')
            WHERE channel_id = {row.channel_id} AND ts = TIMESTAMP '{row.ts}'
            """
        ).fetchdf()
        if train_row.empty:
            continue
        train = train_row.iloc[0]

        worker = worker_features_at(con, db, row.channel_id, row.ts)
        if worker is None:
            n_worker_none += 1
            print(f"[{row.regime}] channel={row.channel_id} ts={row.ts}: worker вернул None (нет событий в окне)")
            continue

        diffs = []
        for f in OWN_CHANNEL_FEATURES:
            t_val = train[f]
            w_val = worker[f]
            if f == "seconds_since_last_event":
                match = abs(float(t_val) - float(w_val)) < 1.0
            elif f == "current_state":
                match = str(t_val) == str(w_val)
            else:
                match = int(t_val) == int(w_val)
            if not match:
                mismatch_counts[f] += 1
                if len(mismatch_examples[f]) < 3:
                    mismatch_examples[f].append((row.channel_id, str(row.ts), t_val, w_val))
                diffs.append(f"{f}: train={t_val!r} worker={w_val!r}")

        n_compared += 1
        if diffs:
            print(f"[{row.regime}] channel={row.channel_id} ts={row.ts}: MISMATCH -> {'; '.join(diffs)}")
        else:
            n_ok += 1

    print("\n--- summary ---")
    print(f"compared: {n_compared}, fully matching: {n_ok}, worker returned None (no events in 7d window): {n_worker_none}")
    for f in OWN_CHANNEL_FEATURES:
        print(f"{f}: {mismatch_counts[f]} mismatches, examples={mismatch_examples[f]}")


if __name__ == "__main__":
    main()
