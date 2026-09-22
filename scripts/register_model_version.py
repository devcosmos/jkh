"""Модуль дообучения прогнозных моделей на новых данных (раздел 8 ЖКХ.md, «дополнительные
требования» — по согласованию с заказчиком, не блокирует MVP).

Обучение самой модели на новых данных уже делают scripts/train_model*.py (по одному на
трек) — этот скрипт закрывает вторую половину «модуля дообучения», которой раньше не было:
регистрацию нового обученного артефакта как новой активной ModelVersion в БД, с деактивацией
предыдущей той же категории. Раньше ModelVersion создавалась только один раз вручную внутри
import_analysis_to_db.py — повторно обучить и подключить модель без правки кода было нельзя.

Полный цикл дообучения:
  1. Обучить новую модель локально (см. docs/documentation/data-audit.md, раздел с описанием пайплайна):
       python3 scripts/train_model.py            # насос/вентилятор
       python3 scripts/train_model_дым_газ.py     # дым/газ
     Каждый скрипт сохраняет .cbm и model_report_<track>.json в docs/documentation/analysis/.
  2. Скопировать новый .cbm в data/ (тот каталог, который читает worker, REPLAY_DATA_DIR):
       cp docs/documentation/analysis/catboost_насос_вентилятор.cbm data/catboost_насос_вентилятор.cbm
  3. Зарегистрировать новую версию в БД этим скриптом (деактивирует старую того же трека):
       JKH_DATABASE_URL=... python3 scripts/register_model_version.py \\
         --track насос_вентилятор \\
         --threshold 0.55 \\
         --train-start 2024-01-01 --train-end 2025-01-01
  4. Перезапустить worker, чтобы он загрузил новый файл модели (сам он .cbm не перечитывает
     на лету — грузит один раз при старте, см. replay_worker.py:load_track):
       docker compose restart worker

Метрики (--report) необязательны, но рекомендуются — тот же report.json, что печатает
train_model*.py, целиком копируется в ModelVersion.metrics (как и при первичном импорте,
см. import_analysis_to_db.py:load_extra_metrics).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import ModelVersion  # noqa: E402

TRACK_SENSOR_TYPES = {
    "насос_вентилятор": "Состояние насоса,Состояние вентилятора",
    "дым_газ": "Датчик дыма,Газовый датчик",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--track", required=True, choices=sorted(TRACK_SENSOR_TYPES), help="насос_вентилятор | дым_газ")
    p.add_argument("--threshold", type=float, required=True, help="Рабочий порог по эпизодной оценке")
    p.add_argument("--train-start", required=True, help="YYYY-MM-DD — начало периода обучения")
    p.add_argument("--train-end", required=True, help="YYYY-MM-DD — конец периода обучения")
    p.add_argument("--report", help="Путь к model_report_<track>.json (метрики) — необязательно")
    p.add_argument("--name", help="Имя версии — по умолчанию catboost_<track>_v<N+1>")
    p.add_argument(
        "--artifact-path",
        help="Путь артефакта для записи в БД (справочно) — по умолчанию data/catboost_<track>.cbm",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    sensor_types = TRACK_SENSOR_TYPES[args.track]

    metrics = None
    if args.report:
        metrics = json.loads(Path(args.report).read_text(encoding="utf-8"))

    db = SessionLocal()
    try:
        previous = list(
            db.scalars(
                select(ModelVersion).where(
                    ModelVersion.sensor_types == sensor_types, ModelVersion.is_active.is_(True)
                )
            )
        )
        for mv in previous:
            mv.is_active = False
            db.add(mv)

        version_n = len(list(db.scalars(select(ModelVersion).where(ModelVersion.sensor_types == sensor_types)))) + 1

        new_version = ModelVersion(
            name=args.name or f"catboost_{args.track}_v{version_n}",
            sensor_types=sensor_types,
            trained_at=dt.datetime.now(dt.timezone.utc),
            train_period_start=dt.datetime.fromisoformat(args.train_start).replace(tzinfo=dt.timezone.utc),
            train_period_end=dt.datetime.fromisoformat(args.train_end).replace(tzinfo=dt.timezone.utc),
            threshold=args.threshold,
            metrics=metrics,
            artifact_path=args.artifact_path or f"data/catboost_{args.track}.cbm",
            is_active=True,
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        for mv in previous:
            print(f"деактивирована предыдущая версия: id={mv.id}, name={mv.name}", file=sys.stderr)
        print(f"зарегистрирована новая активная версия: id={new_version.id}, name={new_version.name}", file=sys.stderr)
        print("не забудьте перезапустить worker, чтобы он подхватил новый файл модели: docker compose restart worker", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
