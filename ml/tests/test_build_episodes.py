"""Тесты границ эпизода и правила флаппинга ml/features/build_episodes.py (docs/documentation/label-policy.md,
раздел 2; docs/documentation/data-audit.md, разделы 6.1-6.6): run-length по состоянию, left/right
censoring, порог >10 переходов в «Неисправен» за календарные сутки = технический инцидент.

Запуск: source .venv/bin/activate && python3 -m pytest ml/tests/ -v
"""
import csv
import importlib.util
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

FEATURES_DIR = Path(__file__).resolve().parent.parent / "features"


def _load_build_episodes_module():
    spec = importlib.util.spec_from_file_location("build_episodes", FEATURES_DIR / "build_episodes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHANNEL_HEADER = ["ид_канала_данных", "тип_инж_системы", "тип_датчика", "тег_инженерной_системы", "название_датчика"]
EVENT_HEADER = ["ид_события", "ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"]


def _write_channels_csv(path: Path, channel_ids: list[int]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CHANNEL_HEADER)
        for cid in channel_ids:
            w.writerow([cid, "Насосная подсистема", "Состояние насоса", f"test-{cid}.", f"Тест {cid}"])


def _write_events_csv(path: Path, rows: list[tuple[int, str, str, str]]) -> None:
    """rows: (channel_id, date 'YYYY-MM-DD', time 'HH:MM:SS', state)"""
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(EVENT_HEADER)
        for i, (cid, date, time_, state) in enumerate(rows):
            w.writerow([1_000_000 + i, cid, date, time_, "f", state])


@pytest.fixture
def episodes_df(tmp_path, monkeypatch):
    module = _load_build_episodes_module()

    channel_ids = [2001, 2002, 2003, 2004]
    _write_channels_csv(tmp_path / "справочник_каналов_датчиков.csv", channel_ids)

    rows = [
        # 2001: одна нормальная короткая заявка-эпизод, не censored, день без флаппинга.
        (2001, "2024-01-01", "08:00:00", "Норма"),
        (2001, "2024-01-02", "09:00:00", "Неисправен"),
        (2001, "2024-01-02", "09:05:00", "Норма"),
        # 2002: первая запись канала уже "Неисправен" -> left-censored.
        (2002, "2024-03-01", "00:00:00", "Неисправен"),
        (2002, "2024-03-01", "05:00:00", "Норма"),
        # 2003: последняя запись канала "Неисправен", восстановления не было -> right-censored.
        (2003, "2024-05-01", "00:00:00", "Норма"),
        (2003, "2024-05-01", "10:00:00", "Неисправен"),
    ]
    # 2004: 12 независимых стартов "Неисправен" за один день -> флаппинг (порог >10/сутки).
    for i in range(12):
        minute = i * 2
        rows.append((2004, "2024-02-01", f"{minute:02d}:00:00", "Неисправен"))
        rows.append((2004, "2024-02-01", f"{minute:02d}:00:30", "Норма"))

    _write_events_csv(tmp_path / "ext-journal-2024.csv", rows)

    monkeypatch.setattr(module, "DATASET_DIR", tmp_path)

    con = duckdb.connect()
    con.execute(
        f"CREATE VIEW channels AS SELECT * FROM read_csv_auto("
        f"'{tmp_path / 'справочник_каналов_датчиков.csv'}', header=true)"
    )
    module.build_episodes(con, ["2024"], ["Состояние насоса"])
    return con.execute("SELECT * FROM episodes ORDER BY ид_канала_данных, start_time").fetchdf()


def test_normal_episode_not_censored_not_flapping(episodes_df):
    ep = episodes_df[episodes_df["ид_канала_данных"] == 2001].iloc[0]
    assert not ep["left_censored"]
    assert not ep["right_censored"]
    assert not ep["is_flapping_incident"]
    assert ep["recovered_to_state"] == "Норма"


def test_left_censored_when_first_record_already_faulty(episodes_df):
    ep = episodes_df[episodes_df["ид_канала_данных"] == 2002].iloc[0]
    assert ep["left_censored"]
    assert not ep["right_censored"]


def test_right_censored_when_never_recovers(episodes_df):
    ep = episodes_df[episodes_df["ид_канала_данных"] == 2003].iloc[0]
    assert ep["right_censored"]
    assert pd.isna(ep["recovered_at"])
    assert not ep["left_censored"]


def test_flapping_day_flags_all_episodes_that_day(episodes_df):
    eps = episodes_df[episodes_df["ид_канала_данных"] == 2004]
    assert len(eps) == 12
    assert eps["is_flapping_incident"].all()
    assert (eps["n_episode_starts_that_day"] == 12).all()


def test_flapping_does_not_leak_to_other_channels(episodes_df):
    for cid in (2001, 2002, 2003):
        eps = episodes_df[episodes_df["ид_канала_данных"] == cid]
        assert not eps["is_flapping_incident"].any()
