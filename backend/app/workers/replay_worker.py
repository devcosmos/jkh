"""Фоновый worker: replay истории + живой инференс (раздел 3 ТЗ MVP, раздел 8 плана).

Продвигает виртуальное время по часовым тикам, "доставляет" события из заранее
подготовленных компактных файлов-потоков (ml/features/build_replay_feed.py,
2025-07-01..2026-06-30, честно "невиданный" моделью test-период) в оперативную таблицу
`channel_events` (скользящее окно 7 суток — раздел 7.2 плана), затем на каждом тике считает
признаки напрямую в Postgres (те же признаки, что при обучении — ml/features/build_features*.py)
и прогоняет через уже обученный CatBoost — отдельно для каждого из двух независимо
оцениваемых треков (тема 18 CSV с ответами организаторов: «два независимых результата,
оцениваются отдельно») — насос/вентилятор и дым/газ.

Курсор возобновления — таблица `replay_state` (простая сохраняемая точка вместо брокера
сообщений, раздел 3 ТЗ MVP), общая для обоих треков: оба фида покрывают один и тот же
период, поэтому виртуальное время едино. При перезапуске worker продолжает с последнего
сохранённого виртуального времени, а не с начала.

Контракт признаков, загрузка моделей (CatBoost/IsolationForest) и объяснение прогноза
(SHAP + аномальность) вынесены в app/ml/ (шаг 3 реструктуризации каталогов) — этот модуль
отвечает только за доставку событий и оркестрацию тика (ingest -> features -> score ->
persist), сам не знает деталей контракта признаков или формата файлов моделей.

Известное ограничение — холодный старт: первые ~7 виртуальных суток после чистого
разворачивания (пустой replay_state) признаки по каждому каналу занижены, потому что
channel_events ещё не накопил историю, которую обучение всегда видело с 2024 года. Осознанно
не исправлено — см. docs/documentation/Технические_заметки.md, запись от 22 сентября.
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.db import SessionLocal  # noqa: E402
from app.ml.explain import compute_anomaly_signal, explain_prediction  # noqa: E402
from app.ml.features import ALL_FEATURES, compute_features_for_channel  # noqa: E402
from app.ml.models import DATA_DIR, TRACKS, load_track_runtime  # noqa: E402
from app.models.entities import (  # noqa: E402
    Channel,
    ChannelEvent,
    Prediction,
    ReplayState,
    RiskCase,
)
from app.models.enums import RiskCaseStatus  # noqa: E402

TICK = dt.timedelta(hours=int(os.environ.get("REPLAY_TICK_HOURS", "1")))
RETENTION = dt.timedelta(days=7)
SLEEP_SECONDS = float(os.environ.get("REPLAY_SLEEP_SECONDS", "2"))


def load_feed(track) -> pd.DataFrame:
    df = pd.read_parquet(DATA_DIR / f"replay_feed_{track.name}.parquet")
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
    # event_id — тай-брейк порядка вставки для событий одного канала с одинаковым event_time
    # (секундная точность источника): ChannelEvent.id (автоинкремент) получает правильный
    # хронологический порядок только если вставка идёт в этом порядке — см.
    # ml/features/build_replay_feed.py и compute_features_for_channel (app/ml/features.py,
    # ORDER BY ..., id).
    return df.sort_values(["event_time", "event_id"]).reset_index(drop=True)


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
    # Сохранить состояние на момент вытеснения — иначе LAG(state) в compute_features_for_channel
    # теряет prev_state у самой старой оставшейся записи и граничный переход состояния молча
    # выпадает из n_transitions_* (см. ChannelRetentionWatermark).
    db.execute(
        text(
            """
            INSERT INTO channel_retention_watermark (channel_id, last_pruned_state, last_pruned_event_time)
            SELECT DISTINCT ON (channel_id) channel_id, state, event_time
            FROM channel_events
            WHERE event_time < :cutoff
            ORDER BY channel_id, event_time DESC
            ON CONFLICT (channel_id) DO UPDATE
            SET last_pruned_state = EXCLUDED.last_pruned_state,
                last_pruned_event_time = EXCLUDED.last_pruned_event_time
            WHERE EXCLUDED.last_pruned_event_time > channel_retention_watermark.last_pruned_event_time
            """
        ),
        {"cutoff": cutoff},
    )
    db.execute(delete(ChannelEvent).where(ChannelEvent.event_time < cutoff))


# Минимальное автозакрытие: без него за виртуальный год по тысячам каналов накапливается
# нереалистичный объём вечно открытых риск-кейсов (113 тыс. при лучших по recall порогах —
# см. docs/documentation/Технические_заметки.md, запись от 20 сентября). Если по риск-кейсу не было нового прогноза выше
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


def score_and_record(
    db,
    track,
    threshold: float,
    model,
    anomaly_bundle: dict,
    channel: Channel,
    features: dict,
    tick_end: dt.datetime,
    model_version_id: int,
) -> float:
    row = [[features[f] if f != "тип_датчика" else channel.sensor_type for f in ALL_FEATURES]]
    proba = float(model.predict_proba(row)[0][1])

    if proba >= threshold:
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
                threshold_used=threshold,
                explanation={**explain_prediction(model, row), "anomaly": anomaly},
                data_quality_flag="ok",
                created_at=tick_end,
            )
        )
    return proba


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
    feed = pd.concat(feeds, ignore_index=True).sort_values(["event_time", "event_id"]).reset_index(drop=True)
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
                features = compute_features_for_channel(db, channel, tick_end, rt.track.sensor_types)
                if features is None:
                    continue
                proba = score_and_record(
                    db, rt.track, rt.threshold, rt.model, rt.anomaly_bundle, channel, features, tick_end,
                    rt.model_version_id,
                )
                if proba >= rt.threshold:
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
