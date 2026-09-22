"""Загрузка обученных моделей: конфигурация треков и чтение CatBoost/IsolationForest с
диска + активной ModelVersion из БД. Вынесено из app/workers/replay_worker.py
реструктуризацией каталогов (шаг 3) — worker теперь только вызывает load_track_runtime,
сам не знает, откуда берутся файлы моделей.

Рабочий порог каждого трека — не «жёсткий» 0.7/0.5, а лучшая точка эпизодной оценки, та же,
что и при бэкфилле (scripts/data/import_analysis_to_db.py); см. artifacts/model_report_*.md,
раздел 3. Источник порога — активная ModelVersion.threshold в БД (пишется
scripts/maintenance/register_model_version.py / import_analysis_to_db.py), а не переменная
окружения: раньше регистрация новой версии могла молча разойтись с порогом, который worker
реально применяет, потому что тот читался из TRACKS/env независимо от БД.
DEFAULT_THRESHOLDS ниже — запасной вариант только для случая, когда у активной версии
threshold не задан.
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import joblib
from catboost import CatBoostClassifier
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Channel, ModelVersion

# Каталог с файлами моделей и replay-фидами worker'а — в контейнере том же, что в
# docker-compose.yml монтирует ./artifacts (объединённый каталог: демокомплект моделей +
# обучающие отчёты/витрины, см. корневой .gitignore).
DATA_DIR = Path(os.environ.get("REPLAY_DATA_DIR", "/artifacts"))


@dataclass(frozen=True)
class Track:
    name: str  # суффикс файлов в /artifacts — совпадает с ml/features/build_replay_feed.py и train_model*.py
    category: str  # RiskCase.category / Prediction.category — тот же, что в scripts/data/import_analysis_to_db.py
    sensor_types: list[str]


TRACKS = [
    Track(
        name="насос_вентилятор",
        category="sensor_failure_pump_fan",
        sensor_types=["Состояние насоса", "Состояние вентилятора"],
    ),
    Track(
        name="дым_газ",
        category="sensor_failure_smoke_gas",
        sensor_types=["Датчик дыма", "Газовый датчик"],
    ),
]

# Запасной порог — только если у активной ModelVersion threshold не задан (например, версия
# зарегистрирована в обход register_model_version.py). Нормальный путь — порог из БД.
DEFAULT_THRESHOLDS = {
    "насос_вентилятор": float(os.environ.get("REPLAY_THRESHOLD_PUMP_FAN", "0.55")),
    "дым_газ": float(os.environ.get("REPLAY_THRESHOLD_SMOKE_GAS", "0.53")),
}


@dataclass
class TrackRuntime:
    track: Track
    model: CatBoostClassifier
    anomaly_bundle: dict
    channels: list[Channel]
    model_version_id: int
    threshold: float


def load_track_runtime(db: Session, track: Track) -> TrackRuntime:
    model_path = DATA_DIR / f"catboost_{track.name}.cbm"
    print(f"[{track.name}] loading model from {model_path}...", file=sys.stderr)
    model = CatBoostClassifier()
    model.load_model(str(model_path))

    anomaly_path = DATA_DIR / f"isolation_forest_{track.name}.joblib"
    print(f"[{track.name}] loading anomaly model from {anomaly_path}...", file=sys.stderr)
    anomaly_bundle = joblib.load(anomaly_path)

    channels = list(db.scalars(select(Channel).where(Channel.sensor_type.in_(track.sensor_types))))
    model_version = db.scalar(
        select(ModelVersion).where(
            ModelVersion.is_active.is_(True),
            ModelVersion.sensor_types == ",".join(track.sensor_types),
        )
    )
    if model_version is None:
        print(
            f"[{track.name}] no active model_version in DB — run scripts/data/import_analysis_to_db.py first",
            file=sys.stderr,
        )
        sys.exit(1)

    if model_version.threshold is not None:
        threshold = model_version.threshold
    else:
        threshold = DEFAULT_THRESHOLDS[track.name]
        print(
            f"[{track.name}] active model_version {model_version.id} has no threshold — "
            f"falling back to default {threshold}",
            file=sys.stderr,
        )
    return TrackRuntime(
        track=track,
        model=model,
        anomaly_bundle=anomaly_bundle,
        channels=channels,
        model_version_id=model_version.id,
        threshold=threshold,
    )
