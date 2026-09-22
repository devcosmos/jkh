"""Сезонность (app.services.analytics.seasonal_breakdown) раньше сравнивала сырые суммы
эпизодов по календарному месяцу без нормализации. При данных, охватывающих неполное число
лет (например, 2024-01 .. 2025-06), первое полугодие набирает вдвое больше периодов
наблюдения (2 года), чем второе (1 год) — сырая сумма делает второе полугодие «спокойнее»,
чем оно есть на самом деле. avg_episodes_per_year должен нормализовать это."""
import datetime as dt

from app.models.entities import Channel, IncidentEpisode, Object
from app.services.analytics import seasonal_breakdown


def _episode(channel_id: int, year: int, month: int, day: int = 15) -> IncidentEpisode:
    return IncidentEpisode(
        channel_id=channel_id,
        sensor_type="Состояние насоса",
        start_time=dt.datetime(year, month, day, tzinfo=dt.timezone.utc),
        is_flapping_incident=False,
    )


def _setup(db_session) -> int:
    obj = Object(name="Объект для сезонности")
    db_session.add(obj)
    db_session.flush()
    channel = Channel(external_channel_id=9001, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    return channel.id


def test_uneven_year_range_is_normalized_by_years_observed(db_session):
    channel_id = _setup(db_session)
    # Данные 2024-01 .. 2025-06: январь встречается дважды (2024, 2025), июль — один раз (2024).
    # По одному эпизоду в каждом январе (итого 2) и по одному в единственном июле (итого 1) —
    # сырые суммы почти равны, а реальная частота (в среднем за год) одинакова: 1.0 в обоих.
    db_session.add(_episode(channel_id, 2024, 1))
    db_session.add(_episode(channel_id, 2025, 1))
    db_session.add(_episode(channel_id, 2024, 7))
    db_session.add(_episode(channel_id, 2025, 6, day=30))  # граница диапазона данных
    db_session.commit()

    rows = {r["month"]: r for r in seasonal_breakdown(db_session, None)}

    assert rows[1]["episode_count"] == 2
    assert rows[1]["years_observed"] == 2
    assert rows[1]["avg_episodes_per_year"] == 1.0

    assert rows[7]["episode_count"] == 1
    assert rows[7]["years_observed"] == 1
    assert rows[7]["avg_episodes_per_year"] == 1.0

    # Декабрь попадает в диапазон один раз (2024) — второй раз, декабрь 2025, уже за
    # пределами данных (те заканчиваются в июне 2025). Эпизодов в декабре не было.
    assert rows[12]["years_observed"] == 1
    assert rows[12]["avg_episodes_per_year"] == 0.0
    assert rows[12]["episode_count"] == 0


def test_no_episodes_returns_all_zero_without_crashing(db_session):
    rows = seasonal_breakdown(db_session, None)
    assert len(rows) == 12
    assert all(r["episode_count"] == 0 and r["avg_episodes_per_year"] is None for r in rows)
