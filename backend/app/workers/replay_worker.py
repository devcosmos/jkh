"""Фоновый worker: replay истории + живой инференс (раздел 3 ТЗ MVP, раздел 8 плана).

Продвигает виртуальное время по часовым тикам, "доставляет" события из заранее
подготовленного компактного файла-потока (scripts/build_replay_feed.py — насос/вентилятор,
2025-07-01..2026-06-30, честно "невиданный" моделью test-период) в оперативную таблицу
`channel_events` (скользящее окно 7 суток — раздел 7.2 плана), затем на каждом тике считает
признаки для всех каналов насос/вентилятор напрямую в Postgres (те же признаки, что при
обучении — scripts/build_features.py) и прогоняет через уже обученный CatBoost.

Курсор возобновления — таблица `replay_state` (простая сохраняемая точка вместо брокера
сообщений, раздел 3 ТЗ MVP). При перезапуске worker продолжает с последнего сохранённого
виртуального времени, а не с начала.

Порог 0.7 — тот же провизорный операционный порог, что и при бэкфилле
(scripts/import_analysis_to_db.py); он НЕ удовлетворяет целевым Precision/Recall — см.
docs/analysis/model_report_насос_вентилятор.md.
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier
from sqlalchemy import delete, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    AuditLog,
    Channel,
    ChannelEvent,
    MaintenanceRequest,
    ModelVersion,
    Prediction,
    ReplayState,
    RiskCase,
)
from app.models.enums import MaintenanceRequestStatus, RiskCaseStatus  # noqa: E402

FEED_PATH = Path(os.environ.get("REPLAY_FEED_PATH", "/data/replay_feed_насос_вентилятор.parquet"))
MODEL_PATH = Path(os.environ.get("REPLAY_MODEL_PATH", "/data/catboost_насос_вентилятор.cbm"))
TICK = dt.timedelta(hours=int(os.environ.get("REPLAY_TICK_HOURS", "1")))
RETENTION = dt.timedelta(days=7)
SLEEP_SECONDS = float(os.environ.get("REPLAY_SLEEP_SECONDS", "2"))
ALERT_THRESHOLD = float(os.environ.get("REPLAY_THRESHOLD", "0.7"))

NUM_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "seconds_since_last_event",
    "n_neighbors_in_fault", "frac_neighbors_in_fault",
]
CAT_FEATURES = ["current_state", "тип_датчика"]
ALL_FEATURES = NUM_FEATURES + CAT_FEATURES

# Раздел 10 плана реализации: шаблон рекомендации по типу датчика — обязательное условие
# автосоздания черновика ("существует подходящий шаблон рекомендации").
WORK_TYPE_BY_SENSOR_TYPE = {
    "Состояние насоса": "Диагностика и техническое обслуживание насоса",
    "Состояние вентилятора": "Диагностика и техническое обслуживание вентилятора",
    "Датчик дыма": "Диагностика дымового извещателя",
    "Газовый датчик": "Диагностика газового датчика",
}


def build_draft_justification(channel: Channel, risk_case: RiskCase, features: dict, proba: float, tick_end: dt.datetime) -> str:
    object_name = channel.object.name if channel.object is not None else "не определён"
    window_end = tick_end + dt.timedelta(hours=24)
    return (
        f"Автоматически сформировано по риск-кейсу #{risk_case.id} (правило раздела 10 плана реализации).\n"
        f"Устройство/канал: {channel.display_name or channel.external_channel_id} ({channel.sensor_type}).\n"
        f"Объект: {object_name}.\n"
        f"Категория риска: {risk_case.category}.\n"
        f"Вероятность: {proba:.2f} в окне {tick_end:%Y-%m-%d %H:%M}–{window_end:%Y-%m-%d %H:%M} (UTC).\n"
        f"Наблюдаемые признаки: состояние={features['current_state']}, "
        f"событий за 7 сут={features['n_events_7d']}, переходов за 24ч={features['n_transitions_24h']}, "
        f"с последнего события={features['seconds_since_last_event']:.0f} сек.\n"
        f"Основание: прогноз модели превысил операционный порог {ALERT_THRESHOLD:.2f} "
        f"(целевые Precision/Recall не достигнуты — см. docs/analysis/model_report_насос_вентилятор.md).\n"
        f"Срок: нормативный регламент не определён — требуется назначение диспетчером."
    )


def maybe_create_draft_request(db, channel: Channel, risk_case: RiskCase, features: dict, proba: float, tick_end: dt.datetime) -> None:
    """Автосоздание черновика заявки при открытии нового риск-кейса (раздел 10 плана).

    Условие создания и дедупликация — по устройству/каналу, виду работы и активному
    риск-кейсу, а не по ID прогноза: повторный расчёт на уже открытом риск-кейсе не должен
    сюда попадать (вызывается только из ветки создания НОВОГО RiskCase в score_and_record).
    """
    if proba < settings.auto_draft_risk_threshold:
        return  # риск не превышает установленный порог автосоздания (раздел 10 плана)

    work_type = WORK_TYPE_BY_SENSOR_TYPE.get(channel.sensor_type)
    if work_type is None:
        return  # нет подходящего шаблона рекомендации для этого типа датчика

    existing = db.scalar(
        select(MaintenanceRequest).where(
            MaintenanceRequest.risk_case_id == risk_case.id,
            MaintenanceRequest.work_type == work_type,
            MaintenanceRequest.status.not_in(
                [MaintenanceRequestStatus.rejected, MaintenanceRequestStatus.cancelled]
            ),
        )
    )
    if existing is not None:
        return

    request = MaintenanceRequest(
        risk_case_id=risk_case.id,
        work_type=work_type,
        justification=build_draft_justification(channel, risk_case, features, proba, tick_end),
        priority=risk_case.priority,
        recommended_by=None,
        status=MaintenanceRequestStatus.draft,
        created_at=tick_end,
    )
    db.add(request)
    db.flush()
    db.add(
        AuditLog(
            user_id=None,
            role=None,
            entity_type="maintenance_request",
            entity_id=request.id,
            old_state=None,
            new_state={"status": request.status.value, "source": "auto_worker"},
            reason=f"Автосоздание по открытию риск-кейса #{risk_case.id}",
        )
    )


def load_feed() -> pd.DataFrame:
    df = pd.read_parquet(FEED_PATH)
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


def score_and_record(db, model: CatBoostClassifier, channel: Channel, features: dict, tick_end: dt.datetime, model_version_id: int) -> float:
    row = [[features[f] if f != "тип_датчика" else channel.sensor_type for f in ALL_FEATURES]]
    proba = float(model.predict_proba(row)[0][1])

    if proba >= ALERT_THRESHOLD:
        risk_case = db.scalar(
            select(RiskCase).where(
                RiskCase.channel_id == channel.id,
                RiskCase.status.in_([RiskCaseStatus.new, RiskCaseStatus.observing, RiskCaseStatus.dispatched]),
            )
        )
        if risk_case is None:
            risk_case = RiskCase(
                channel_id=channel.id,
                category="sensor_failure",
                status=RiskCaseStatus.new,
                priority="high" if proba >= 0.85 else "medium",
                opened_at=tick_end,
            )
            db.add(risk_case)
            db.flush()
            maybe_create_draft_request(db, channel, risk_case, features, proba, tick_end)
        db.add(
            Prediction(
                channel_id=channel.id,
                risk_case_id=risk_case.id,
                model_version_id=model_version_id,
                category="sensor_failure",
                probability=proba,
                window_start=tick_end,
                window_end=tick_end + dt.timedelta(hours=24),
                threshold_used=ALERT_THRESHOLD,
                explanation={"live": True, "worker": "replay_worker"},
                data_quality_flag="ok",
                created_at=tick_end,
            )
        )
    return proba


def main() -> None:
    print(f"loading model from {MODEL_PATH}...", file=sys.stderr)
    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))

    print(f"loading feed from {FEED_PATH}...", file=sys.stderr)
    feed = load_feed()
    print(f"feed: {len(feed)} events, {feed.event_time.min()} .. {feed.event_time.max()}", file=sys.stderr)

    db = SessionLocal()
    channels = db.scalars(
        select(Channel).where(Channel.sensor_type.in_(["Состояние насоса", "Состояние вентилятора"]))
    ).all()
    channel_map = {c.external_channel_id: c.id for c in channels}
    model_version = db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    if model_version is None:
        print("no active model_version in DB — run scripts/import_analysis_to_db.py first", file=sys.stderr)
        sys.exit(1)

    virtual_time = get_or_init_virtual_time(db, feed)
    feed_end = feed["event_time"].max().to_pydatetime()
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
        for channel in channels:
            features = compute_features_for_channel(db, channel, tick_end)
            if features is None:
                continue
            proba = score_and_record(db, model, channel, features, tick_end, model_version.id)
            if proba >= ALERT_THRESHOLD:
                n_alerts += 1

        virtual_time = tick_end
        db.execute(
            text("UPDATE replay_state SET virtual_time = :vt, updated_at = now() WHERE id = 1"),
            {"vt": virtual_time},
        )
        db.commit()
        print(f"tick {virtual_time}: {n_alerts} channels above threshold", file=sys.stderr)
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
