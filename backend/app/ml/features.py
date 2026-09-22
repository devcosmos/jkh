"""Контракт признаков worker'а: тот же набор и те же имена, что использует обучение
(ml/features/build_features*.py в корне репозитория — офлайн-пайплайн, не импортируется
отсюда). Раньше жил внутри app/workers/replay_worker.py вперемешку с доставкой событий и
циклом replay — вынесен в отдельный модуль реструктуризацией каталогов (шаг 3), чтобы
контракт признаков, загрузка моделей и объяснения были одним пакетом (app/ml/), а worker
оставался тонким (доставка событий + вызов ml).

Известное расхождение с обучением — не исправлено сознательно, см.
docs/documentation/Технические_заметки.md и scripts/maintenance/check_worker_feature_parity.py:
n_neighbors_* здесь ищет соседей только внутри своего трека (см. фильтр sensor_types в
compute_features_for_channel), как и обучающая витрина.
"""
import datetime as dt

from sqlalchemy import text

from app.models.entities import Channel

NUM_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]
CAT_FEATURES = ["current_state", "тип_датчика"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES
CAT_FEATURE_IDX = [ALL_FEATURES.index(f) for f in CAT_FEATURES]

FEATURE_LABELS = {
    "n_alarms_1h": "Тревог за 1 час",
    "n_alarms_24h": "Тревог за 24 часа",
    "n_alarms_7d": "Тревог за 7 суток",
    "n_transitions_1h": "Переходов состояния за 1 час",
    "n_transitions_24h": "Переходов состояния за 24 часа",
    "n_transitions_7d": "Переходов состояния за 7 суток",
    "n_events_1h": "Событий за 1 час",
    "n_events_24h": "Событий за 24 часа",
    "n_events_7d": "Событий за 7 суток",
    "seconds_since_last_event": "Время с последнего события",
    "n_neighbors_in_fault": "Соседей в отказе",
    "frac_neighbors_in_fault": "Доля соседей в отказе",
    "current_state": "Текущее состояние",
    "тип_датчика": "Тип датчика",
}


def compute_features_for_channel(
    db, channel: Channel, tick_end: dt.datetime, sensor_types: list[str]
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT
                count(*) FILTER (WHERE event_time > :t1h AND is_alarm) AS n_alarms_1h,
                count(*) FILTER (WHERE event_time > :t24h AND is_alarm) AS n_alarms_24h,
                count(*) FILTER (WHERE is_alarm) AS n_alarms_7d,
                count(*) FILTER (WHERE event_time > :t1h) AS n_events_1h,
                count(*) FILTER (WHERE event_time > :t24h) AS n_events_24h,
                count(*) AS n_events_7d,
                max(event_time) AS last_event_time,
                -- id (PK) как тай-брейк: несколько событий канала с одинаковым event_time
                -- (секундная точность источника) вставляются в правильном хронологическом
                -- порядке (см. replay_worker.load_feed/main — сортировка по event_time,
                -- event_id перед ingest_tick), поэтому больший id внутри одинакового
                -- event_time — более поздняя по факту запись. Без этого тай-брейка
                -- current_state мог разойтись с обучением (build_features.py — тот же
                -- тай-брейк по ид_события).
                (array_agg(state ORDER BY event_time DESC, id DESC))[1] AS current_state
            FROM channel_events
            WHERE channel_id = :cid AND event_time <= :tick_end
            """
        ),
        {"cid": channel.id, "t1h": tick_end - dt.timedelta(hours=1), "t24h": tick_end - dt.timedelta(hours=24), "tick_end": tick_end},
    ).mappings().first()

    if row is None or row["last_event_time"] is None:
        return None

    transitions = db.execute(
        text(
            """
            SELECT event_time, state,
                   LAG(state) OVER (ORDER BY event_time, id) AS prev_state
            FROM channel_events
            WHERE channel_id = :cid AND event_time <= :tick_end
            ORDER BY event_time, id
            """
        ),
        {"cid": channel.id, "tick_end": tick_end},
    ).all()
    watermark_state = db.execute(
        text("SELECT last_pruned_state FROM channel_retention_watermark WHERE channel_id = :cid"),
        {"cid": channel.id},
    ).scalar()

    t1h_cut = tick_end - dt.timedelta(hours=1)
    t24h_cut = tick_end - dt.timedelta(hours=24)
    n_trans_1h = n_trans_24h = n_trans_7d = 0
    for i, (event_time, state, prev_state) in enumerate(transitions):
        if i == 0 and prev_state is None:
            prev_state = watermark_state
        if state != prev_state and prev_state is not None:
            n_trans_7d += 1
            if event_time > t24h_cut:
                n_trans_24h += 1
            if event_time > t1h_cut:
                n_trans_1h += 1

    # Соседи считаются только среди каналов своего трека (насос/вентилятор отдельно от
    # дым/газ) — так же, как в обучающей витрине, где events_raw уже отфильтрован по
    # TARGET_TYPES (ml/features/build_features.py). Без этого фильтра worker подмешивал бы
    # чужой трек в n_neighbors_in_fault (найдено при сверке с
    # scripts/maintenance/check_worker_feature_parity.py).
    neighbors = db.execute(
        text(
            """
            SELECT c.id, (array_agg(ce.state ORDER BY ce.event_time DESC, ce.id DESC))[1] AS state
            FROM channels c
            JOIN channel_events ce ON ce.channel_id = c.id AND ce.event_time <= :tick_end
            WHERE c.location_group = :grp AND c.id != :cid AND c.sensor_type = ANY(:sensor_types)
            GROUP BY c.id
            """
        ),
        {
            "grp": channel.location_group,
            "cid": channel.id,
            "tick_end": tick_end,
            "sensor_types": sensor_types,
        },
    ).all()
    n_neighbors_total = len(neighbors)
    n_neighbors_in_fault = sum(1 for _, s in neighbors if s == "Неисправен")

    return {
        "n_alarms_1h": row["n_alarms_1h"],
        "n_alarms_24h": row["n_alarms_24h"],
        "n_alarms_7d": row["n_alarms_7d"],
        "n_transitions_1h": n_trans_1h,
        "n_transitions_24h": n_trans_24h,
        "n_transitions_7d": n_trans_7d,
        "n_events_1h": row["n_events_1h"],
        "n_events_24h": row["n_events_24h"],
        "n_events_7d": row["n_events_7d"],
        "seconds_since_last_event": (tick_end - row["last_event_time"]).total_seconds(),
        "n_neighbors_in_fault": n_neighbors_in_fault,
        "n_neighbors_total": n_neighbors_total,
        "frac_neighbors_in_fault": n_neighbors_in_fault / max(n_neighbors_total, 1),
        "current_state": str(row["current_state"]),
    }
