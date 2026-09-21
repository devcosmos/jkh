"""Тренд деградации канала (docs/ТЗ_тренд_деградации_канала.md) — доп. сигнал внутри
«Отказ датчика», не «Износ инфраструктуры». По прецеденту test_auto_close_stale_risk_cases.py."""
import datetime as dt

from app.models.entities import Channel, IncidentEpisode, Object, UserObjectAccess
from app.models.enums import UserRole
from app.services.degradation_trend import (
    compute_trend_for_channel,
    compute_trend_for_channels,
    get_as_of,
)

AS_OF = dt.datetime(2026, 6, 30, tzinfo=dt.timezone.utc)


def _channel(db_session, ext_id: int, object_id: int | None = None) -> Channel:
    ch = Channel(external_channel_id=ext_id, sensor_type="Состояние насоса", object_id=object_id)
    db_session.add(ch)
    db_session.flush()
    return ch


def _episode(channel_id: int, start_time: dt.datetime, is_flapping: bool = False) -> IncidentEpisode:
    return IncidentEpisode(
        channel_id=channel_id,
        sensor_type="Состояние насоса",
        start_time=start_time,
        is_flapping_incident=is_flapping,
    )


def _spread(db_session, channel_id: int, n: int, days_ago: int, is_flapping: bool = False) -> None:
    for i in range(n):
        db_session.add(_episode(channel_id, AS_OF - dt.timedelta(days=days_ago, hours=i), is_flapping))


def test_worsening_when_recent_much_higher_than_baseline(db_session):
    ch = _channel(db_session, 1001)
    _spread(db_session, ch.id, 6, days_ago=10)  # recent
    _spread(db_session, ch.id, 2, days_ago=120)  # baseline
    # флаппинг подмешан отдельно — не должен учитываться
    _spread(db_session, ch.id, 50, days_ago=5, is_flapping=True)
    db_session.commit()

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] == 6
    assert result["baseline"] == 2
    assert result["status"] == "worsening"


def test_improving_when_recent_much_lower_than_baseline(db_session):
    ch = _channel(db_session, 1002)
    _spread(db_session, ch.id, 1, days_ago=10)
    _spread(db_session, ch.id, 5, days_ago=120)
    db_session.commit()

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] == 1
    assert result["baseline"] == 5
    assert result["status"] == "improving"


def test_stable_when_recent_close_to_baseline(db_session):
    ch = _channel(db_session, 1003)
    _spread(db_session, ch.id, 3, days_ago=10)
    _spread(db_session, ch.id, 3, days_ago=120)
    db_session.commit()

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] == 3
    assert result["baseline"] == 3
    assert result["status"] == "stable"


def test_insufficient_data_below_minimum_total_is_not_reported_as_stable(db_session):
    ch = _channel(db_session, 1004)
    _spread(db_session, ch.id, 1, days_ago=10)
    _spread(db_session, ch.id, 1, days_ago=120)
    db_session.commit()

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] == 1
    assert result["baseline"] == 1
    assert result["status"] == "insufficient_data"


def test_filter_is_applied_on_start_time_not_end_time(db_session):
    ch = _channel(db_session, 1005)
    # start_time внутри recent-окна, но end_time далеко за его пределами — должен считаться
    # по start_time.
    ep = _episode(ch.id, AS_OF - dt.timedelta(days=10))
    ep.end_time = AS_OF + dt.timedelta(days=100)
    db_session.add(ep)
    _spread(db_session, ch.id, 3, days_ago=120)
    db_session.commit()

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] == 1
    assert result["baseline"] == 3


def test_as_of_is_derived_from_data_not_wall_clock(db_session):
    """Данные датированы условным прошлым (2026-06-30), а datetime.now() при тестовом
    прогоне — иное (например, реальный 2026-09). get_as_of обязан вернуть дату из данных,
    иначе recent-окно окажется пустым (та же ловушка, что уже была в JournalPage.tsx)."""
    ch = _channel(db_session, 1006)
    _spread(db_session, ch.id, 4, days_ago=10)
    _spread(db_session, ch.id, 1, days_ago=120)
    db_session.commit()

    as_of = get_as_of(db_session)
    assert as_of is not None
    assert as_of != dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    result = compute_trend_for_channel(db_session, ch.id)
    assert result["recent"] > 0 or result["baseline"] > 0
    assert result["status"] != "insufficient_data" or (result["recent"] + result["baseline"]) < 3


def test_batch_matches_per_channel_computation(db_session):
    ch1 = _channel(db_session, 1007)
    ch2 = _channel(db_session, 1008)
    _spread(db_session, ch1.id, 6, days_ago=10)
    _spread(db_session, ch1.id, 2, days_ago=120)
    _spread(db_session, ch2.id, 1, days_ago=10)
    _spread(db_session, ch2.id, 5, days_ago=120)
    db_session.commit()

    batch = compute_trend_for_channels(db_session, [ch1.id, ch2.id])
    single1 = compute_trend_for_channel(db_session, ch1.id)
    single2 = compute_trend_for_channel(db_session, ch2.id)

    assert batch[ch1.id]["recent"] == single1["recent"]
    assert batch[ch1.id]["baseline"] == single1["baseline"]
    assert batch[ch1.id]["status"] == single1["status"]
    assert batch[ch2.id]["status"] == single2["status"]


def test_channel_endpoint_returns_trend(client, db_session, auth_headers):
    ch = _channel(db_session, 1009)
    _spread(db_session, ch.id, 6, days_ago=10)
    _spread(db_session, ch.id, 2, days_ago=120)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get(f"/api/channels/{ch.id}/degradation-trend", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["channel_id"] == ch.id
    assert body["recent_count"] == 6
    assert body["baseline_count"] == 2
    assert body["status"] == "worsening"
    assert body["recent_window_days"] == 90
    assert body["baseline_window_days"] == 90


def test_list_channels_include_trend_adds_field(client, db_session, auth_headers):
    ch = _channel(db_session, 1010)
    _spread(db_session, ch.id, 6, days_ago=10)
    _spread(db_session, ch.id, 2, days_ago=120)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/channels?include_trend=true", headers=headers)
    assert r.status_code == 200
    rows = {c["id"]: c for c in r.json()}
    assert rows[ch.id]["degradation_trend"] is not None
    assert rows[ch.id]["degradation_trend"]["status"] == "worsening"


def test_list_channels_without_include_trend_omits_field(client, db_session, auth_headers):
    ch = _channel(db_session, 1011)
    _spread(db_session, ch.id, 6, days_ago=10)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/channels", headers=headers)
    assert r.status_code == 200
    rows = {c["id"]: c for c in r.json()}
    assert rows[ch.id]["degradation_trend"] is None


def test_dashboard_summary_includes_top_worsening_channels(client, db_session, auth_headers):
    ch1 = _channel(db_session, 2001)
    ch2 = _channel(db_session, 2002)
    _spread(db_session, ch1.id, 6, days_ago=10)  # worsening, delta 4
    _spread(db_session, ch1.id, 2, days_ago=120)
    _spread(db_session, ch2.id, 9, days_ago=10)  # worsening, delta 7 -> ranked first
    _spread(db_session, ch2.id, 2, days_ago=120)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/dashboard/summary", headers=headers)
    assert r.status_code == 200
    top = r.json()["top_worsening_channels"]
    assert [t["channel_id"] for t in top][:2] == [ch2.id, ch1.id]
    assert top[0]["recent_count"] == 9
    assert top[0]["baseline_count"] == 2


def test_degradation_trend_respects_object_access_matrix(client, db_session, auth_headers):
    from app.models.entities import User

    obj = Object(name="Недоступный объект")
    db_session.add(obj)
    db_session.flush()
    other_obj = Object(name="Доступный объект")
    db_session.add(other_obj)
    db_session.commit()

    ch = _channel(db_session, 1012, object_id=obj.id)
    _spread(db_session, ch.id, 6, days_ago=10)
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher, username="trend-restricted")
    user = db_session.query(User).filter_by(username="trend-restricted").one()
    db_session.add(UserObjectAccess(user_id=user.id, object_id=other_obj.id))
    db_session.commit()

    r = client.get(f"/api/channels/{ch.id}/degradation-trend", headers=headers)
    assert r.status_code == 403
