"""ML-06 (analys_and_todo.md): контрактный тест offline (обучающая витрина) против runtime
(compute_features_for_channel, та же функция, что использует worker) на маленьких
детерминированных фикстурах — backend/tests/fixtures/parity/. CI не имеет доступа к полным
artifacts/features_*.parquet и artifacts/replay_feed_*.parquet (регенерируемые обучающие
артефакты по 90-670 МБ, исключены из Git политикой хранения — см. корневой .gitignore).
backend/tests/fixtures/parity/generate_fixtures.py вырезает маленький (несколько КБ)
детерминированный срез из настоящих артефактов — координаты (канал, момент) не случайны и
включают каналы с группами одинакового event_time и «холодный старт» (первые сутки фида
канала), а не только «удобные» примеры. Обновляется вручную при пересчёте артефактов, не
регенерируется тестом.

Оба трека, все собственные признаки контракта. Производственное вытеснение — настоящий
prune_old_events, не ручная имитация: эквивалентно повторным тикам worker'а благодаря
монотонному upsert watermark (последний пробег — не раньше предыдущего), поэтому один вызов
prune_old_events(db, ts) с cutoff=ts-RETENTION даёт то же состояние БД, что и множество
промежуточных тиков.

Не проверяется здесь:
- n_neighbors_in_fault / n_neighbors_total / frac_neighbors_in_fault — offline считает их по
  реальному location_group канала, который приходит из закрытого
  dataset/справочник_каналов_датчиков.csv (не в Git, недоступен в CI). Числовая офлайн/рантайм
  сверка соседей возможна только локально, с приватным датасетом
  (scripts/maintenance/check_worker_feature_parity.py). Алгоритмическая корректность фильтра
  по треку покрыта синтетическим тестом без dataset/ —
  test_retention_watermark_transitions.py::test_neighbors_scoped_to_own_track.
- in_fault_now — offline знает восстановление эпизода заранее (вся история на диске), runtime
  намеренно вычисляет реалтайм-приближение без доступа к будущему (см. ML-05). Расхождение
  здесь ожидаемо, это не нарушение контракта."""
import datetime as dt
from pathlib import Path

import duckdb
import pytest
from sqlalchemy import text

from app.ml.features import compute_features_for_channel
from app.models.entities import Channel

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "parity"
RETENTION = dt.timedelta(days=7)

TRACK_SENSOR_TYPES = {
    "насос_вентилятор": ["Состояние насоса", "Состояние вентилятора"],
    "дым_газ": ["Датчик дыма", "Газовый датчик"],
}
OWN_CHANNEL_FEATURES = [
    "n_alarms_1h", "n_alarms_24h", "n_alarms_7d",
    "n_transitions_1h", "n_transitions_24h", "n_transitions_7d",
    "n_events_1h", "n_events_24h", "n_events_7d",
    "current_state", "seconds_since_last_event",
]


def _load_fixture(track: str):
    con = duckdb.connect()
    feed = con.execute(
        f"SELECT * FROM read_parquet('{FIXTURES_DIR / f'feed_{track}.parquet'}') ORDER BY event_time, event_id"
    ).fetchdf()
    feed["event_time"] = feed["event_time"].dt.tz_localize(dt.timezone.utc)
    expected = con.execute(
        f"SELECT * FROM read_parquet('{FIXTURES_DIR / f'expected_{track}.parquet'}') ORDER BY channel_id, ts"
    ).fetchdf()
    return feed, expected


def _runtime_features_at(db, feed, channel_id: int, ts: dt.datetime, sensor_types: list[str]) -> dict | None:
    """Пересобирает БД так, как её видел бы worker к моменту ts: только настоящая история
    канала (event_time <= ts), настоящее вытеснение (prune_old_events), настоящая функция
    признаков — не переписана заново, чтобы не завести отдельный источник расхождений."""
    db.execute(text("TRUNCATE TABLE channel_events, channel_retention_watermark RESTART IDENTITY CASCADE"))
    db.execute(text("TRUNCATE TABLE channels RESTART IDENTITY CASCADE"))
    channel = Channel(external_channel_id=channel_id, sensor_type=sensor_types[0])
    db.add(channel)
    db.flush()

    from app.models.entities import ChannelEvent

    events = feed[(feed["channel_id"] == channel_id) & (feed["event_time"] <= ts)]
    if not events.empty:
        db.bulk_insert_mappings(
            ChannelEvent,
            [
                dict(
                    channel_id=channel.id,
                    event_time=row.event_time.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                    state=row.state,
                    is_alarm=bool(row.is_alarm),
                )
                for row in events.itertuples()
            ],
        )
    db.commit()

    from app.workers.replay_worker import prune_old_events

    prune_old_events(db, ts)
    db.commit()

    return compute_features_for_channel(db, channel, ts, sensor_types)


def _is_cold_start(feed, channel_id: int, ts: dt.datetime) -> bool:
    """LIMIT-01 (analys_and_todo.md, принятое ограничение): committed replay_feed_*.parquet
    начинается с REPLAY_START (2025-07-01 или позже для конкретного канала) — offline же
    считает признаки по полной истории с 2024 года. В первые сутки после первого события
    канала В ФИДЕ у runtime заведомо меньше предыстории, чем у offline (например,
    n_transitions_* offline включает переход, случившийся ДО начала фида, которого у runtime
    физически нет и не может быть без полного приватного датасета) — это не нарушение
    контракта, а уже задокументированное и осознанно принятое ограничение холодного старта."""
    channel_start = feed.loc[feed["channel_id"] == channel_id, "event_time"].min()
    return ts < (channel_start + dt.timedelta(days=1))


def _compare_track(db_session, track: str) -> list[str]:
    feed, expected = _load_fixture(track)
    sensor_types = TRACK_SENSOR_TYPES[track]
    mismatches = []

    for row in expected.itertuples():
        ts = row.ts.to_pydatetime().replace(tzinfo=dt.timezone.utc)
        runtime = _runtime_features_at(db_session, feed, row.channel_id, ts, sensor_types)
        if runtime is None:
            mismatches.append(f"channel={row.channel_id} ts={ts}: runtime вернул None, offline ожидает признаки")
            continue
        if _is_cold_start(feed, row.channel_id, ts):
            # Всё равно вызываем runtime выше (не пропускаем точку целиком) — падение или
            # None здесь означало бы настоящий баг, не просто известный количественный сдвиг
            # холодного старта. Числовое сравнение пропускаем осознанно (LIMIT-01).
            continue
        for f in OWN_CHANNEL_FEATURES:
            expected_val = getattr(row, f)
            actual_val = runtime[f]
            if f == "seconds_since_last_event":
                ok = abs(float(expected_val) - float(actual_val)) < 1.0
            elif f == "current_state":
                ok = str(expected_val) == str(actual_val)
            else:
                ok = int(expected_val) == int(actual_val)
            if not ok:
                mismatches.append(
                    f"channel={row.channel_id} ts={ts} {f}: offline={expected_val!r} runtime={actual_val!r}"
                )
    return mismatches


@pytest.mark.parametrize("track", sorted(TRACK_SENSOR_TYPES))
def test_offline_runtime_feature_parity(db_session, track):
    mismatches = _compare_track(db_session, track)
    assert not mismatches, f"[{track}] {len(mismatches)} расхождений offline/runtime:\n" + "\n".join(mismatches)
