"""ML-05 (analys_and_todo.md): поведение realtime-контракта признаков для каналов без
недавних событий и для каналов, уже находящихся в устойчивом отказе — оба случая offline
(label-policy.md) определяет иначе, чем worker мог бы вычислить без доступа к будущему.

Длительное молчание: канал без событий в сохранённом (после retention) окне — worker
не может отличить "канал спокоен" от "канал сломан и перестал слать данные", в offline
такого канала просто нет в почасовой сетке (она строится по фактическим событиям). Оба
случая одинаково не дают признаков — compute_features_for_channel возвращает None, и вызывающий
код (replay_worker.main) пропускает канал на этом тике, не пытаясь оценить его вслепую.

Текущая неисправность: label-policy.md, раздел 4 — "Датчик, уже находящийся в отказе в
момент t, показывается отдельно и не входит в набор «исправных», для которых прогнозируется
новый отказ". Offline знает восстановление эпизода заранее (вся история заранее на диске);
worker — нет. in_fault_now — realtime-приближение той же идеи: устойчивый (не короче debounce
в 1 час — label-policy.md, раздел 2) пробег state="Неисправен", не подпадающий под дневной
флаппинг (тот же порог 10/сутки, что и ml/features/build_episodes.py)."""
import datetime as dt

from app.ml.features import compute_features_for_channel
from app.models.entities import Channel, ChannelEvent
from app.workers.replay_worker import RETENTION, prune_old_events

NOW = dt.datetime(2026, 1, 10, 15, 0, tzinfo=dt.timezone.utc)  # 15:00 — день уже начался


def _setup(db_session) -> Channel:
    channel = Channel(external_channel_id=51001, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    return channel


def test_silent_channel_beyond_retention_returns_no_features(db_session):
    """Единственное событие канала старше 7 суток — после prune_old_events для него не
    остаётся ни одной строки в channel_events; compute_features_for_channel должен вернуть
    None (а не притворяться, что признаки посчитаны из пустого окна)."""
    channel = _setup(db_session)
    db_session.add(
        ChannelEvent(
            channel_id=channel.id, event_time=NOW - RETENTION - dt.timedelta(days=30), state="Норма",
        )
    )
    db_session.commit()

    prune_old_events(db_session, NOW)
    db_session.commit()

    assert compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"]) is None


def test_never_seen_channel_returns_no_features(db_session):
    """Канал вообще без единого события — тот же результат, что и после полного вытеснения
    ретеншеном: None, не 0/пустая строка."""
    channel = _setup(db_session)
    db_session.commit()

    assert compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"]) is None


def test_in_fault_now_false_before_debounce(db_session):
    """Переход в "Неисправен" только что произошёл (меньше часа назад) — ещё не устойчивый
    эпизод по debounce label-policy.md, in_fault_now должен быть False."""
    channel = _setup(db_session)
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=3), state="Норма"))
    db_session.flush()
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(minutes=30), state="Неисправен")
    )
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["current_state"] == "Неисправен"
    assert features["in_fault_now"] is False


def test_in_fault_now_true_after_debounce(db_session):
    """Тот же переход, но два часа назад — debounce (1 час) пройден, не флаппинг ->
    in_fault_now должен быть True."""
    channel = _setup(db_session)
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=5), state="Норма"))
    db_session.flush()
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=2), state="Неисправен")
    )
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["in_fault_now"] is True


def test_in_fault_now_true_when_left_censored(db_session):
    """Единственное сохранённое событие уже "Неисправен" — переход В это состояние не виден
    в пределах сохранённой истории (левоцензурировано). label-policy.md: такой эпизод не
    считается новым, но длительность заведомо не меньше сохранённой истории — debounce
    консервативно считаем пройденным, in_fault_now должен быть True."""
    channel = _setup(db_session)
    db_session.add(
        ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=2), state="Неисправен")
    )
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["in_fault_now"] is True


def test_in_fault_now_false_when_flapping_today(db_session):
    """11 входов в "Неисправен" за сегодня (порог флаппинга — 10/сутки, тот же, что
    ml/features/build_episodes.py) — даже если последний пробег уже не короче debounce,
    это технический инцидент, а не устойчивый отказ. in_fault_now должен быть False."""
    channel = _setup(db_session)
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    t = day_start + dt.timedelta(minutes=1)
    # Затравка, чтобы у самого первого входа в "Неисправен" был prev_state (иначе первая
    # строка вообще не считается переходом — см. compute_features_for_channel).
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=t, state="Норма"))
    db_session.flush()
    t += dt.timedelta(minutes=2)

    for i in range(11):  # ровно 11 входов в "Неисправен" за сегодня — выше порога 10
        db_session.add(ChannelEvent(channel_id=channel.id, event_time=t, state="Неисправен"))
        db_session.flush()
        t += dt.timedelta(minutes=2)
        if i < 10:  # последний пробег остаётся "Неисправен" — устойчиво, дольше debounce
            db_session.add(ChannelEvent(channel_id=channel.id, event_time=t, state="Норма"))
            db_session.flush()
            t += dt.timedelta(minutes=2)
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, t + dt.timedelta(hours=2), ["Состояние насоса"])
    assert features["current_state"] == "Неисправен"
    assert features["in_fault_now"] is False


def test_in_fault_now_false_when_state_is_normal(db_session):
    channel = _setup(db_session)
    db_session.add(ChannelEvent(channel_id=channel.id, event_time=NOW - dt.timedelta(hours=5), state="Норма"))
    db_session.commit()

    features = compute_features_for_channel(db_session, channel, NOW, ["Состояние насоса"])
    assert features["in_fault_now"] is False
