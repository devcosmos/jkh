"""Два расхождения между compute_features_for_channel (worker) и обучающей витриной
(scripts/build_features.py), найденные scripts/check_worker_feature_parity.py:

1. Граница retention теряла переход состояния — LAG(state) для самой старой сохранённой
   записи в channel_events не видит уже удалённого предшественника. prune_old_events теперь
   пишет ChannelRetentionWatermark перед удалением, а расчёт переходов сеет им prev_state.
2. Соседи считались по всем каналам location_group без учёта трека, тогда как обучающая
   витрина строится отдельно по каналам своего трека (насос/вентилятор отдельно от
   дым/газ).

Третье, отдельное расхождение (current_state на дублирующихся timestamp) и его фикс —
tie-break по id (см. compute_features_for_channel и scripts/build_replay_feed.py) — покрыты
ниже, test_tie_break_by_id_for_duplicate_timestamps."""
import datetime as dt

from app.models.entities import Channel, ChannelEvent, ChannelRetentionWatermark
from app.workers.replay_worker import RETENTION, compute_features_for_channel, prune_old_events

NOW = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)


def _setup(db_session):
    channel = Channel(external_channel_id=42002, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    return channel


def test_transition_at_retention_boundary_is_not_lost(db_session):
    channel = _setup(db_session)
    cutoff = NOW - RETENTION

    # Событие непосредственно перед границей retention — сменит состояние на "Неисправен",
    # затем будет вытеснено prune_old_events.
    db_session.add(
        ChannelEvent(
            channel_id=channel.id, event_time=cutoff - dt.timedelta(hours=1),
            state="Неисправен", is_alarm=True,
        )
    )
    # Единственное оставшееся после retention событие — назад в "Норма". Без watermark
    # LAG(state) для этой строки увидит prev_state=None и транзишн потеряется.
    db_session.add(
        ChannelEvent(
            channel_id=channel.id, event_time=cutoff + dt.timedelta(hours=1),
            state="Норма", is_alarm=False,
        )
    )
    db_session.commit()

    prune_old_events(db_session, NOW)
    db_session.commit()

    assert db_session.get(ChannelRetentionWatermark, channel.id) is not None
    remaining = db_session.query(ChannelEvent).filter_by(channel_id=channel.id).count()
    assert remaining == 1

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["n_transitions_7d"] == 1
    assert features["current_state"] == "Норма"


def test_no_watermark_no_change_in_behavior(db_session):
    """Канал без предшествующей истории (никогда ничего не вытеснялось) — прежнее поведение:
    первая запись не считается переходом."""
    channel = _setup(db_session)
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=1), state="Норма")
    )
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["n_transitions_7d"] == 0


def test_tie_break_by_id_for_duplicate_timestamps(db_session):
    """Исходный журнал изредка логирует два события одного канала с одинаковым event_time
    (секундная точность) — обычно настоящий быстрый переход состояния, не дубль записи
    (~95% таких групп содержат разные state — см. scripts/build_features.py). ID
    (автоинкремент, отражает порядок вставки — см. load_feed/main: сортировка фида по
    event_time, event_id перед ingest_tick) — тай-брейк: current_state должен быть от записи
    с большим id, и переход между двумя такими записями должен засчитаться, а не потеряться."""
    channel = _setup(db_session)
    tied_ts = NOW - dt.timedelta(hours=1)
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=2), state="Норма")
    )
    db_session.flush()
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=tied_ts, state="Неисправен"))
    db_session.flush()
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=tied_ts, state="Обесточен"))
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["current_state"] == "Обесточен"
    assert features["n_transitions_7d"] == 2  # Норма->Неисправен, Неисправен->Обесточен


def test_neighbors_scoped_to_own_track(db_session):
    """Обучающая витрина строит соседей только среди каналов своего трека (events_raw уже
    отфильтрован по TARGET_TYPES в scripts/build_features.py). Сосед из другого трека
    (дым/газ) не должен попадать в n_neighbors_* для канала насос/вентилятор."""
    channel = _setup(db_session)
    channel.location_group = "group-1"

    same_track_neighbor = Channel(
        external_channel_id=42003, sensor_type="Состояние вентилятора", location_group="group-1"
    )
    other_track_neighbor = Channel(
        external_channel_id=42004, sensor_type="Датчик дыма", location_group="group-1"
    )
    db_session.add_all([same_track_neighbor, other_track_neighbor])
    db_session.flush()

    for c in (same_track_neighbor, other_track_neighbor):
        db_session.add(
            ChannelEvent(channel_id=c.id, event_time=NOW - dt.timedelta(hours=1), state="Неисправен")
        )
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=1), state="Норма")
    )
    db_session.commit()

    features = compute_features_for_channel(
        db_session, channel, NOW, ["Состояние насоса", "Состояние вентилятора"]
    )
    assert features["n_neighbors_total"] == 1
    assert features["n_neighbors_in_fault"] == 1
