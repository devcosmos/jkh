"""Наполняет реальную БД (backend/app/models) готовыми артефактами из docs/analysis/ и
dataset/, чтобы UI показывал реальные данные вместо пустых списков.

Импортирует: каналы (насос/вентилятор/дым/газ), объекты (без привязки к каналам — открытый
пробел, см. data-audit.md), очищенные+флаппинг-эпизоды, одну версию модели (CatBoost,
насос/вентилятор), и риск-кейсы/прогнозы, полученные группировкой прогонов предупреждений
на test-периоде при пороге 0.7 (выбран ради управляемого объёма демо-данных — при пороге 0.5
получилось бы 1.4 млн сырых строк из-за низкой калибровки модели, см. model_report;
порог 0.7 НЕ является порогом, удовлетворяющим целевым Precision/Recall — это только для
демонстрации сквозного сценария).

Запуск (после открытия SSH-туннеля к Postgres на сервере):
  JKH_DATABASE_URL=postgresql+psycopg://jkh:<пароль>@localhost:5555/jkh \
    source .venv/bin/activate && python3 scripts/import_analysis_to_db.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    Channel,
    IncidentEpisode,
    ModelVersion,
    Object,
    Prediction,
    RiskCase,
)
from app.models.enums import EpisodeSource, RiskCaseStatus  # noqa: E402

DATASET_DIR = ROOT / "dataset"
ANALYSIS_DIR = ROOT / "docs" / "analysis"
CORE_TYPES = ["Состояние насоса", "Состояние вентилятора", "Датчик дыма", "Газовый датчик"]
ALERT_THRESHOLD = 0.7
LABEL_POLICY_VERSION = "2026-09-15"


def import_channels(con: duckdb.DuckDBPyConnection, db) -> dict[int, int]:
    print("importing channels...", file=sys.stderr)
    type_list_sql = ", ".join(f"'{t}'" for t in CORE_TYPES)
    rows = con.execute(
        f"""
        SELECT ид_канала_данных, тип_инж_системы, тип_датчика, тег_инженерной_системы,
               название_датчика,
               regexp_replace(тег_инженерной_системы, '\\d+\\.$', '') AS location_group
        FROM read_csv_auto('{DATASET_DIR / "справочник_каналов_датчиков.csv"}', header=true)
        WHERE тип_датчика IN ({type_list_sql})
        """
    ).fetchall()

    mapping: dict[int, int] = {}
    batch = []
    for ext_id, subsystem, sensor_type, tag, name, group in rows:
        batch.append(
            dict(
                external_channel_id=ext_id,
                sensor_type=sensor_type,
                subsystem=subsystem,
                location_tag=tag,
                location_group=group,
                display_name=name,
            )
        )
    db.bulk_insert_mappings(Channel, batch)
    db.commit()
    for ch in db.query(Channel.id, Channel.external_channel_id).all():
        mapping[ch.external_channel_id] = ch.id
    print(f"  {len(mapping)} channels imported", file=sys.stderr)
    return mapping


def import_objects(con: duckdb.DuckDBPyConnection, db) -> None:
    print("importing objects (без привязки к каналам — открытый пробел)...", file=sys.stderr)
    rows = con.execute(
        f"""
        SELECT ид_объект, иерархия_уровень, родитель, вид_объекта, диспетчерское_название_объекта
        FROM read_csv_auto('{DATASET_DIR / "справочник_объектов_диспетчер.csv"}', header=true)
        """
    ).fetchall()

    id_map: dict[int, int] = {}
    for ext_id, level, _parent, kind, name in rows:
        obj = Object(external_id=str(ext_id), hierarchy_level=level, kind=kind, name=name)
        db.add(obj)
        db.flush()
        id_map[ext_id] = obj.id
    for ext_id, _level, parent, _kind, _name in rows:
        if parent is not None and parent in id_map:
            db.query(Object).filter_by(id=id_map[ext_id]).update({"parent_id": id_map[parent]})
    db.commit()
    print(f"  {len(id_map)} objects imported", file=sys.stderr)


def import_episodes(channel_map: dict[int, int], db) -> None:
    print("importing incident episodes...", file=sys.stderr)
    con = duckdb.connect()
    total = 0
    for name in ["насос_вентилятор_2024_2026", "дым_газ_2024_2026"]:
        path = ANALYSIS_DIR / f"episodes_{name}.parquet"
        if not path.exists():
            continue
        rows = con.execute(
            f"""
            SELECT ид_канала_данных, тип_датчика, start_time, recovered_at,
                   is_flapping_incident, left_censored, right_censored
            FROM read_parquet('{path}')
            """
        ).fetchall()
        batch = []
        for ext_id, sensor_type, start_time, end_time, is_flap, left_c, right_c in rows:
            channel_id = channel_map.get(ext_id)
            if channel_id is None:
                continue
            batch.append(
                dict(
                    channel_id=channel_id,
                    sensor_type=sensor_type,
                    start_time=start_time,
                    end_time=end_time,
                    source=EpisodeSource.sensor_state,
                    is_flapping_incident=bool(is_flap),
                    left_censored=bool(left_c),
                    right_censored=bool(right_c),
                    label_policy_version=LABEL_POLICY_VERSION,
                )
            )
        if batch:
            db.bulk_insert_mappings(IncidentEpisode, batch)
            db.commit()
            total += len(batch)
        print(f"  {name}: {len(batch)} episodes", file=sys.stderr)
    print(f"  {total} episodes imported total", file=sys.stderr)


def import_model_version(db) -> int:
    print("importing model version...", file=sys.stderr)
    report = json.loads((ANALYSIS_DIR / "model_report_насос_вентилятор.json").read_text())
    mv = ModelVersion(
        name="catboost_насос_вентилятор_v1_frac_neighbors",
        sensor_types="Состояние насоса,Состояние вентилятора",
        trained_at=dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc),
        train_period_start=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        train_period_end=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        threshold=ALERT_THRESHOLD,
        metrics={
            "roc_auc_test": report["catboost"].get("roc_auc_test"),
            "pr_auc_test": report["catboost"].get("pr_auc_test"),
            "target_precision": report["target_precision"],
            "target_recall": report["target_recall"],
            "target_met": False,
            "note": (
                "Целевые метрики Precision>0.7/Recall>0.5 НЕ достигнуты — см. "
                "docs/analysis/model_report_насос_вентилятор.md, раздел 3.1-3.2"
            ),
        },
        artifact_path="docs/analysis/catboost_насос_вентилятор.cbm",
        is_active=True,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    print(f"  model_version id={mv.id}", file=sys.stderr)
    return mv.id


def import_risk_cases_and_predictions(channel_map: dict[int, int], model_version_id: int, db) -> None:
    print(f"building alert runs at threshold {ALERT_THRESHOLD} (test split only)...", file=sys.stderr)
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE VIEW s AS
        SELECT * FROM read_parquet('{ANALYSIS_DIR / "scored_насос_вентилятор.parquet"}')
        WHERE split = 'test'
        """
    )
    con.execute(f"CREATE VIEW alerts AS SELECT *, (score >= {ALERT_THRESHOLD}) AS is_alert FROM s")
    con.execute(
        """
        CREATE VIEW ordered AS
        SELECT *, LAG(is_alert) OVER (PARTITION BY channel_id ORDER BY ts) AS prev_alert
        FROM alerts
        """
    )
    con.execute(
        """
        CREATE VIEW runs AS
        SELECT *, SUM(CASE WHEN is_alert IS DISTINCT FROM prev_alert THEN 1 ELSE 0 END)
            OVER (PARTITION BY channel_id ORDER BY ts ROWS UNBOUNDED PRECEDING) AS run_id
        FROM ordered
        """
    )
    run_members = con.execute(
        """
        SELECT channel_id, run_id, ts, score
        FROM runs WHERE is_alert
        ORDER BY channel_id, run_id, ts
        """
    ).fetchall()

    current_key = None
    current_channel_ext = None
    risk_case = None
    predictions_batch = []
    n_risk_cases = 0

    def flush_predictions():
        if predictions_batch:
            db.bulk_insert_mappings(Prediction, predictions_batch)
            predictions_batch.clear()

    for channel_ext, run_id, ts, score in run_members:
        key = (channel_ext, run_id)
        channel_id = channel_map.get(channel_ext)
        if channel_id is None:
            continue
        if key != current_key:
            flush_predictions()
            priority = "high" if score >= 0.85 else "medium"
            risk_case = RiskCase(
                channel_id=channel_id,
                category="sensor_failure",
                status=RiskCaseStatus.new,
                priority=priority,
                opened_at=ts,
            )
            db.add(risk_case)
            db.flush()
            current_key = key
            n_risk_cases += 1
        window_end = ts + dt.timedelta(hours=24)
        predictions_batch.append(
            dict(
                channel_id=channel_id,
                risk_case_id=risk_case.id,
                model_version_id=model_version_id,
                category="sensor_failure",
                probability=float(score),
                window_start=ts,
                window_end=window_end,
                threshold_used=ALERT_THRESHOLD,
                explanation={
                    "note": "Глобальная важность признаков модели, не индивидуальное объяснение",
                    "top_features": ["seconds_since_last_event", "n_events_7d", "тип_датчика"],
                },
                data_quality_flag="ok",
                created_at=ts,
            )
        )
        if len(predictions_batch) >= 5000:
            flush_predictions()
            db.commit()

    flush_predictions()
    db.commit()
    print(f"  {n_risk_cases} risk cases, {len(run_members)} predictions imported", file=sys.stderr)


def main() -> None:
    db = SessionLocal()
    con = duckdb.connect()
    try:
        channel_map = import_channels(con, db)
        import_objects(con, db)
        import_episodes(channel_map, db)
        model_version_id = import_model_version(db)
        import_risk_cases_and_predictions(channel_map, model_version_id, db)
        print("DONE", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
