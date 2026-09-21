"""Фоновый worker: replay истории + живой инференс (раздел 3 ТЗ MVP, раздел 8 плана).

Продвигает виртуальное время по часовым тикам, "доставляет" события из заранее
подготовленных компактных файлов-потоков (scripts/build_replay_feed.py,
2025-07-01..2026-06-30, честно "невиданный" моделью test-период) в оперативную таблицу
`channel_events` (скользящее окно 7 суток — раздел 7.2 плана), затем на каждом тике считает
признаки напрямую в Postgres (те же признаки, что при обучении — scripts/build_features*.py)
и прогоняет через уже обученный CatBoost — отдельно для каждого из двух независимо
оцениваемых треков (тема 18 CSV с ответами организаторов: «два независимых результата,
оцениваются отдельно») — насос/вентилятор и дым/газ.

Курсор возобновления — таблица `replay_state` (простая сохраняемая точка вместо брокера
сообщений, раздел 3 ТЗ MVP), общая для обоих треков: оба фида покрывают один и тот же
период, поэтому виртуальное время едино. При перезапуске worker продолжает с последнего
сохранённого виртуального времени, а не с начала.

Рабочий порог каждого трека — не «жёсткий» 0.7/0.5, а лучшая точка эпизодной оценки, та же,
что и при бэкфилле (scripts/import_analysis_to_db.py); см. TRACKS ниже и
docs/analysis/model_report_*.md, раздел 3.
"""
import datetime as dt
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    Channel,
    ChannelEvent,
    ModelVersion,
    Prediction,
    ReplayState,
    RiskCase,
)
from app.models.enums import RiskCaseStatus  # noqa: E402

DATA_DIR = Path(os.environ.get("REPLAY_DATA_DIR", "/data"))
TICK = dt.timedelta(hours=int(os.environ.get("REPLAY_TICK_HOURS", "1")))
RETENTION = dt.timedelta(days=7)
SLEEP_SECONDS = float(os.environ.get("REPLAY_SLEEP_SECONDS", "2"))


@dataclass(frozen=True)
class Track:
    name: str  # суффикс файлов в /data — совпадает с scripts/build_replay_feed.py и train_model*.py
    category: str  # RiskCase.category / Prediction.category — тот же, что в scripts/import_analysis_to_db.py
    sensor_types: list[str]
    threshold: float  # лучшая точка эпизодной оценки, не целевой 0.7/0.5 — см. model_report_*.md, раздел 3


TRACKS = [
    Track(
        name="насос_вентилятор",
        category="sensor_failure_pump_fan",
        sensor_types=["Состояние насоса", "Состояние вентилятора"],
        threshold=float(os.environ.get("REPLAY_THRESHOLD_PUMP_FAN", "0.55")),
    ),
    Track(
        name="дым_газ",
        category="sensor_failure_smoke_gas",
        sensor_types=["Датчик дыма", "Газовый датчик"],
        threshold=float(os.environ.get("REPLAY_THRESHOLD_SMOKE_GAS", "0.53")),
    ),
]

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


def explain_prediction(model: CatBoostClassifier, row: list[list]) -> dict:
    """SHAP-объяснение конкретного прогноза (не глобальная важность признаков) —
    per-tick, той же моделью, что и сам прогноз (get_feature_importance(..., ShapValues)).
    Топ-5 признаков по модулю вклада, со знаком (в сторону риска / против)."""
    pool = Pool(row, cat_features=CAT_FEATURE_IDX)
    shap_row = model.get_feature_importance(pool, type="ShapValues")[0]
    base_value = float(shap_row[-1])
    contributions = list(zip(ALL_FEATURES, shap_row[:-1], row[0]))
    contributions.sort(key=lambda t: abs(t[1]), reverse=True)
    return {
        "method": "catboost_shap",
        "base_value": round(base_value, 4),
        "top_features": [
            {
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                "value": round(float(value), 3) if isinstance(value, (int, float)) else str(value),
                "contribution": round(float(contribution), 4),
            }
            for name, contribution, value in contributions[:5]
        ],
    }


def compute_anomaly_signal(anomaly_bundle: dict, features: dict) -> dict:
    """Независимый от CatBoost сигнал: IsolationForest без учителя на тех же поведенческих
    признаках (scripts/train_anomaly_model.py). Не заменяет прогноз модели, а дополняет его —
    может отметить необычное поведение канала, не похожее ни на один известный сценарий
    отказа в разметке (в отличие от CatBoost, который находит только виденные паттерны)."""
    model = anomaly_bundle["model"]
    feature_names = anomaly_bundle["features"]
    x = [[features[f] for f in feature_names]]
    score = float(model.decision_function(x)[0])  # выше — более «нормально»
    is_outlier = bool(model.predict(x)[0] == -1)
    return {"method": "isolation_forest", "score": round(score, 4), "is_outlier": is_outlier}


def load_feed(track: Track) -> pd.DataFrame:
    df = pd.read_parquet(DATA_DIR / f"replay_feed_{track.name}.parquet")
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
    return df.sort_values("event_time").reset_index(drop=True)


def get_or_init_virtual_time(db, feed: pd.DataFrame) -> dt.datetime:
    state = db.get(ReplayState, 1)
    if state is None:
        start = feed["event_time"].min() - TICK
        state = ReplayState(id=1, virtual_time=start)
        db.add(state)
        db.commit()
    return state.virtual_time


def ingest_tick(db, feed: pd.DataFrame, cursor: int, tick_end: dt.datetime, channel_map: dict[int, int]) -> int:
    """Вставляет события с event_time <= tick_end начиная с позиции cursor. Возвращает новый cursor."""
    n = len(feed)
    batch = []
    while cursor < n and feed.at[cursor, "event_time"] <= tick_end:
        row = feed.iloc[cursor]
        channel_id = channel_map.get(int(row["channel_id"]))
        if channel_id is not None:
            batch.append(
                dict(
                    channel_id=channel_id,
                    event_time=row["event_time"].to_pydatetime(),
                    state=row["state"],
                    is_alarm=bool(row["is_alarm"]),
                )
            )
        cursor += 1
    if batch:
        db.bulk_insert_mappings(ChannelEvent, batch)
    return cursor


def prune_old_events(db, tick_end: dt.datetime) -> None:
    cutoff = tick_end - RETENTION
    db.execute(delete(ChannelEvent).where(ChannelEvent.event_time < cutoff))


# Минимальное автозакрытие: без него за виртуальный год по тысячам каналов накапливается
# нереалистичный объём вечно открытых риск-кейсов (113 тыс. при лучших по recall порогах —
# см. docs/Статус.md, запись от 20 сентября). Если по риск-кейсу не было нового прогноза выше
# порога дольше этого окна — считаем ситуацию нормализовавшейся и закрываем его сами
# (упрощение MVP: без подтверждения фактического ремонта диспетчером).
AUTO_CLOSE_AFTER = dt.timedelta(hours=48)


def close_stale_risk_cases(db, tick_end: dt.datetime) -> int:
    result = db.execute(
        text(
            """
            WITH last_pred AS (
                SELECT risk_case_id, max(created_at) AS last_ts
                FROM predictions
                GROUP BY risk_case_id
            )
            UPDATE risk_cases
            SET status = 'resolved', closed_at = last_pred.last_ts
            FROM last_pred
            WHERE risk_cases.id = last_pred.risk_case_id
              AND risk_cases.status IN ('new', 'observing', 'dispatched')
              AND last_pred.last_ts < :cutoff
            """
        ),
        {"cutoff": tick_end - AUTO_CLOSE_AFTER},
    )
    return result.rowcount


def compute_features_for_channel(db, channel: Channel, tick_end: dt.datetime) -> dict | None:
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
                (array_agg(state ORDER BY event_time DESC))[1] AS current_state
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
                   LAG(state) OVER (ORDER BY event_time) AS prev_state
            FROM channel_events
            WHERE channel_id = :cid AND event_time <= :tick_end
            ORDER BY event_time
            """
        ),
        {"cid": channel.id, "tick_end": tick_end},
    ).all()
    t1h_cut = tick_end - dt.timedelta(hours=1)
    t24h_cut = tick_end - dt.timedelta(hours=24)
    n_trans_1h = n_trans_24h = n_trans_7d = 0
    for event_time, state, prev_state in transitions:
        if state != prev_state and prev_state is not None:
            n_trans_7d += 1
            if event_time > t24h_cut:
                n_trans_24h += 1
            if event_time > t1h_cut:
                n_trans_1h += 1

    neighbors = db.execute(
        text(
            """
            SELECT c.id, (array_agg(ce.state ORDER BY ce.event_time DESC))[1] AS state
            FROM channels c
            JOIN channel_events ce ON ce.channel_id = c.id AND ce.event_time <= :tick_end
            WHERE c.location_group = :grp AND c.id != :cid
            GROUP BY c.id
            """
        ),
        {"grp": channel.location_group, "cid": channel.id, "tick_end": tick_end},
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


def score_and_record(
    db,
    track: Track,
    model: CatBoostClassifier,
    anomaly_bundle: dict,
    channel: Channel,
    features: dict,
    tick_end: dt.datetime,
    model_version_id: int,
) -> float:
    row = [[features[f] if f != "тип_датчика" else channel.sensor_type for f in ALL_FEATURES]]
    proba = float(model.predict_proba(row)[0][1])

    if proba >= track.threshold:
        anomaly = compute_anomaly_signal(anomaly_bundle, features)
        risk_case = db.scalar(
            select(RiskCase).where(
                RiskCase.channel_id == channel.id,
                RiskCase.status.in_([RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched]),
            )
        )
        if risk_case is None:
            # Приоритет high не только по высокой вероятности, но и если независимая
            # (не размеченная на тех же отказах) модель отдельно подтверждает необычное
            # поведение — два разных метода согласны, это сильнее одного порога вероятности.
            risk_case = RiskCase(
                channel_id=channel.id,
                category=track.category,
                status=RiskCaseStatus.new,
                priority="high" if (proba >= 0.85 or anomaly["is_outlier"]) else "medium",
                opened_at=tick_end,
            )
            db.add(risk_case)
            db.flush()
        db.add(
            Prediction(
                channel_id=channel.id,
                risk_case_id=risk_case.id,
                model_version_id=model_version_id,
                category=track.category,
                probability=proba,
                window_start=tick_end,
                window_end=tick_end + dt.timedelta(hours=24),
                threshold_used=track.threshold,
                explanation={**explain_prediction(model, row), "anomaly": anomaly},
                data_quality_flag="ok",
                created_at=tick_end,
            )
        )
    return proba


@dataclass
class TrackRuntime:
    track: Track
    model: CatBoostClassifier
    anomaly_bundle: dict
    channels: list[Channel]
    model_version_id: int


def load_track_runtime(db: Session, track: Track) -> TrackRuntime:
    model_path = DATA_DIR / f"catboost_{track.name}.cbm"
    print(f"[{track.name}] loading model from {model_path}...", file=sys.stderr)
    model = CatBoostClassifier()
    model.load_model(str(model_path))

    anomaly_path = DATA_DIR / f"isolation_forest_{track.name}.joblib"
    print(f"[{track.name}] loading anomaly model from {anomaly_path}...", file=sys.stderr)
    anomaly_bundle = joblib.load(anomaly_path)

    channels = list(db.scalars(select(Channel).where(Channel.sensor_type.in_(track.sensor_types))))
    model_version = db.scalar(
        select(ModelVersion).where(
            ModelVersion.is_active.is_(True),
            ModelVersion.sensor_types == ",".join(track.sensor_types),
        )
    )
    if model_version is None:
        print(
            f"[{track.name}] no active model_version in DB — run scripts/import_analysis_to_db.py first",
            file=sys.stderr,
        )
        sys.exit(1)
    return TrackRuntime(
        track=track, model=model, anomaly_bundle=anomaly_bundle, channels=channels, model_version_id=model_version.id
    )


def main() -> None:
    db = SessionLocal()
    runtimes = [load_track_runtime(db, track) for track in TRACKS]

    feeds = []
    for rt in runtimes:
        feed = load_feed(rt.track)
        print(
            f"[{rt.track.name}] feed: {len(feed)} events, {feed.event_time.min()} .. {feed.event_time.max()}",
            file=sys.stderr,
        )
        feeds.append(feed)
    feed = pd.concat(feeds, ignore_index=True).sort_values("event_time").reset_index(drop=True)
    channel_map = {c.external_channel_id: c.id for rt in runtimes for c in rt.channels}

    virtual_time = get_or_init_virtual_time(db, feed)
    feed_end = min(f["event_time"].max().to_pydatetime() for f in feeds)
    cursor = int((feed["event_time"] <= virtual_time).sum())
    print(f"resuming from virtual_time={virtual_time}, cursor={cursor}", file=sys.stderr)

    while True:
        tick_end = virtual_time + TICK
        if tick_end > feed_end:
            print(f"replay reached end of available data ({feed_end}) — idling", file=sys.stderr)
            time.sleep(30)
            continue

        cursor = ingest_tick(db, feed, cursor, tick_end, channel_map)
        prune_old_events(db, tick_end)

        n_alerts = 0
        for rt in runtimes:
            for channel in rt.channels:
                features = compute_features_for_channel(db, channel, tick_end)
                if features is None:
                    continue
                proba = score_and_record(
                    db, rt.track, rt.model, rt.anomaly_bundle, channel, features, tick_end, rt.model_version_id
                )
                if proba >= rt.track.threshold:
                    n_alerts += 1

        n_closed = close_stale_risk_cases(db, tick_end)

        virtual_time = tick_end
        db.execute(
            text("UPDATE replay_state SET virtual_time = :vt, updated_at = now() WHERE id = 1"),
            {"vt": virtual_time},
        )
        db.commit()
        print(f"tick {virtual_time}: {n_alerts} channels above threshold, {n_closed} auto-closed", file=sys.stderr)
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
