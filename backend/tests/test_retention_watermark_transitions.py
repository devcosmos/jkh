"""Граница retention не должна терять переход состояния (см.
scripts/check_worker_feature_parity.py — worker систематически недосчитывал ровно один
переход в n_transitions_*, когда он случался на самой старой сохранённой записи, потому что
LAG(state) для неё не видит уже удалённого предшественника). prune_old_events теперь пишет
ChannelRetentionWatermark перед удалением, а compute_features_for_channel сеет им prev_state
для самой старой оставшейся записи."""
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

    features = compute_features_for_channel(db_session, channel, NOW)
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

    features = compute_features_for_channel(db_session, channel, NOW)
    assert features["n_transitions_7d"] == 0
