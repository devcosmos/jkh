"""Дополняет metrics уже импортированных ModelVersion признаковой важностью и калибровкой,
не трогая остальные данные (risk_cases/predictions) — полный повторный прогон
import_analysis_to_db.py не нужен и не идемпотентен на заполненной БД.

Запуск: JKH_DATABASE_URL=... python3 scripts/maintenance/backfill_model_metrics.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import ModelVersion  # noqa: E402
from import_analysis_to_db import ARTIFACTS_DIR, TRACKS, load_extra_metrics  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        for track in TRACKS:
            mv = db.scalar(
                select(ModelVersion).where(
                    ModelVersion.sensor_types == track.sensor_types,
                    ModelVersion.is_active.is_(True),
                )
            )
            if mv is None:
                print(f"[{track.name}] активная модель не найдена в БД, пропуск", file=sys.stderr)
                continue
            report = json.loads((ARTIFACTS_DIR / f"model_report_{track.name}.json").read_text())
            mv.metrics = {**(mv.metrics or {}), **load_extra_metrics(track, report)}
            db.add(mv)
            print(f"[{track.name}] обновлено: model_version id={mv.id}", file=sys.stderr)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
