"""ML-07 (analys_and_todo.md): активная ModelVersion должна реально определять, какой файл
загружает worker, а не только записывать threshold. Раньше load_track_runtime всегда грузил
фиксированное имя catboost_<track>.cbm независимо от artifact_path в БД, а сам файл никак не
сверялся с записью — можно было получить новую версию в интерфейсе с одним порогом и реальные
прогнозы с моделью, которая физически не менялась (или изменилась без ведома worker'а)."""
import datetime as dt
import hashlib
from pathlib import Path

import pytest

from app.ml import models as models_module
from app.ml.features import ALL_FEATURES
from app.ml.models import TRACKS, _resolve_artifact_path, _verify_artifact_hash, _verify_feature_schema, load_track_runtime
from app.models.entities import Channel, ModelVersion

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts"
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
PUMP_FAN_TRACK = TRACKS[0]


def _real_cbm_path() -> Path:
    return ARTIFACTS_DIR / f"catboost_{PUMP_FAN_TRACK.name}.cbm"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_model_version(db_session, **overrides) -> ModelVersion:
    defaults = dict(
        name="test", sensor_types=",".join(PUMP_FAN_TRACK.sensor_types), trained_at=NOW,
        train_period_start=NOW, train_period_end=NOW, threshold=0.55, is_active=True,
    )
    defaults.update(overrides)
    mv = ModelVersion(**defaults)
    db_session.add(mv)
    db_session.commit()
    db_session.refresh(mv)
    return mv


def test_resolve_artifact_path_uses_basename_under_data_dir(tmp_path):
    """Путь может быть сохранён относительно совсем другого окружения/этапа реструктуризации
    (например, старое "docs/analysis/catboost_x.cbm") — реальный файл всегда ищется в
    DATA_DIR по basename, не по сохранённому полному пути."""
    resolved = _resolve_artifact_path("catboost_default.cbm", "docs/analysis/catboost_другое_имя.cbm")
    assert resolved == models_module.DATA_DIR / "catboost_другое_имя.cbm"


def test_resolve_artifact_path_falls_back_to_default_name():
    resolved = _resolve_artifact_path("catboost_default.cbm", None)
    assert resolved == models_module.DATA_DIR / "catboost_default.cbm"


def test_verify_artifact_hash_passes_on_match(tmp_path):
    f = tmp_path / "model.cbm"
    f.write_bytes(b"contents")
    _verify_artifact_hash(f, hashlib.sha256(b"contents").hexdigest(), "test-track")  # не должно упасть


def test_verify_artifact_hash_exits_on_mismatch(tmp_path):
    f = tmp_path / "model.cbm"
    f.write_bytes(b"contents")
    with pytest.raises(SystemExit):
        _verify_artifact_hash(f, "0" * 64, "test-track")


def test_verify_artifact_hash_skipped_when_no_hash_recorded(tmp_path):
    """Версии, зарегистрированные до появления этого поля (существующие в проде на момент
    ML-07), не должны ломать уже работающий worker — только предупреждение."""
    f = tmp_path / "model.cbm"
    f.write_bytes(b"contents")
    _verify_artifact_hash(f, None, "test-track")  # не должно упасть


def test_verify_feature_schema_passes_on_match():
    class FakeModel:
        feature_names_ = list(ALL_FEATURES)

    _verify_feature_schema(FakeModel(), "test-track")  # не должно упасть


def test_verify_feature_schema_exits_on_mismatch():
    class FakeModel:
        feature_names_ = ["другой", "набор", "признаков"]

    with pytest.raises(SystemExit):
        _verify_feature_schema(FakeModel(), "test-track")


@pytest.mark.skipif(not _real_cbm_path().exists(), reason="artifacts/catboost_*.cbm недоступен")
def test_load_track_runtime_uses_registered_artifact_path_and_hash(db_session, monkeypatch):
    """Сквозной сценарий на настоящем committed-в-Git файле модели (демокомплект): регистрация
    с совпадающим sha256 должна успешно загрузиться, с несовпадающим — отказать до того, как
    worker начнёт считать прогнозы на потенциально не той модели."""
    monkeypatch.setattr(models_module, "DATA_DIR", ARTIFACTS_DIR)
    real_path = _real_cbm_path()
    _make_model_version(
        db_session,
        artifact_path=f"artifacts/catboost_{PUMP_FAN_TRACK.name}.cbm",
        artifact_sha256=_sha256(real_path),
    )

    channel = Channel(external_channel_id=90001, sensor_type=PUMP_FAN_TRACK.sensor_types[0])
    db_session.add(channel)
    db_session.commit()

    runtime = load_track_runtime(db_session, PUMP_FAN_TRACK)
    assert runtime.threshold == 0.55


@pytest.mark.skipif(not _real_cbm_path().exists(), reason="artifacts/catboost_*.cbm недоступен")
def test_load_track_runtime_exits_on_hash_mismatch(db_session, monkeypatch):
    monkeypatch.setattr(models_module, "DATA_DIR", ARTIFACTS_DIR)
    _make_model_version(
        db_session,
        artifact_path=f"artifacts/catboost_{PUMP_FAN_TRACK.name}.cbm",
        artifact_sha256="0" * 64,
    )

    with pytest.raises(SystemExit):
        load_track_runtime(db_session, PUMP_FAN_TRACK)
