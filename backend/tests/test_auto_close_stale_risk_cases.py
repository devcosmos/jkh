"""Минимальное автозакрытие (app.workers.replay_worker.close_stale_risk_cases) — без него
на длинном прогоне по тысячам каналов набегает нереалистичный объём вечно открытых
риск-кейсов (см. docs/Статус.md, запись от 20 сентября). Если по риск-кейсу не было нового
прогноза дольше AUTO_CLOSE_AFTER — кейс закрывается автоматически."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus
from app.workers.replay_worker import close_stale_risk_cases

NOW = dt.datetime(2026, 1, 10, tzinfo=dt.timezone.utc)


def _setup(db_session):
    channel = Channel(external_channel_id=42001, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types="Состояние насоса", trained_at=NOW,
        train_period_start=NOW, train_period_end=NOW, is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    return channel, mv


def _prediction(channel, mv, risk_case, created_at):
    return Prediction(
        channel_id=channel.id, risk_case_id=risk_case.id, model_version_id=mv.id,
        category="sensor_failure_pump_fan", probability=0.9,
        window_start=created_at, window_end=created_at + dt.timedelta(hours=24),
        created_at=created_at,
    )


def test_case_with_no_recent_prediction_is_closed(db_session):
    channel, mv = _setup(db_session)
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=NOW - dt.timedelta(hours=60))
    db_session.add(rc)
    db_session.flush()
    stale_ts = NOW - dt.timedelta(hours=60)
    db_session.add(_prediction(channel, mv, rc, stale_ts))
    db_session.commit()

    n_closed = close_stale_risk_cases(db_session, NOW)
    db_session.commit()

    assert n_closed == 1
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.resolved
    assert rc.closed_at == stale_ts


def test_case_with_recent_prediction_stays_open(db_session):
    channel, mv = _setup(db_session)
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, opened_at=NOW - dt.timedelta(hours=10))
    db_session.add(rc)
    db_session.flush()
    db_session.add(_prediction(channel, mv, rc, NOW - dt.timedelta(hours=10)))
    db_session.commit()

    n_closed = close_stale_risk_cases(db_session, NOW)
    db_session.commit()

    assert n_closed == 0
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.new
    assert rc.closed_at is None


def test_already_rejected_case_is_left_untouched(db_session):
    channel, mv = _setup(db_session)
    rc = RiskCase(
        channel_id=channel.id, status=RiskCaseStatus.rejected,
        opened_at=NOW - dt.timedelta(hours=60), closed_at=NOW - dt.timedelta(hours=59),
    )
    db_session.add(rc)
    db_session.flush()
    db_session.add(_prediction(channel, mv, rc, NOW - dt.timedelta(hours=60)))
    db_session.commit()

    n_closed = close_stale_risk_cases(db_session, NOW)
    db_session.commit()

    assert n_closed == 0
    db_session.refresh(rc)
    assert rc.status == RiskCaseStatus.rejected
    assert rc.closed_at == NOW - dt.timedelta(hours=59)
