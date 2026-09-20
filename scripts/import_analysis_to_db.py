"""Наполняет реальную БД (backend/app/models) готовыми артефактами из docs/analysis/ и
dataset/, чтобы UI показывал реальные данные вместо пустых списков.

Импортирует: объекты, каналы (насос/вентилятор/дым/газ) с привязкой к объекту через поле
`ид_объект` обновлённого `справочник_каналов_датчиков.csv` (до 17 сентября 2026 этой связи
не было — организаторы подтвердили и прислали обновлённый файл, см. тему 4 в
`Город 8. ДЖКХ.xlsx - Вопросы_нормализованные_и_Ответы.csv`), очищенные+флаппинг-эпизоды,
по одной версии модели на каждый из двух независимо оцениваемых треков (тема 18 CSV: «два
независимых результата, оцениваются отдельно») — насос/вентилятор и дым/газ — и риск-кейсы/
прогнозы, полученные группировкой прогонов предупреждений на test-периоде.

Рабочий порог каждого трека — не «жёсткий» 0.7/0.5 (тема 3 CSV: «указанные значения являются
плановыми, а не жёсткими требованиями… если данные не позволяют достичь этих уровней, их
можно снизить, обязательно обосновав»), а лучшая точка по эпизодной оценке
(scripts/evaluate_episodes*.py, docs/analysis/episode_evaluation_*.json) — см. TRACKS ниже.

Запуск (после открытия SSH-туннеля к Postgres на сервере):
  JKH_DATABASE_URL=postgresql+psycopg://jkh:<пароль>@localhost:5555/jkh \
    source .venv/bin/activate && python3 scripts/import_analysis_to_db.py
"""
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
from sqlalchemy import text

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
LABEL_POLICY_VERSION = "2026-09-15"

# Минимальное автозакрытие (без него на годе данных по тысячам каналов набегает
# нереалистичный объём вечно открытых риск-кейсов — 113 тыс. при лучших по recall порогах,
# см. docs/Статус.md, запись от 20 сентября). Если по каналу не было нового прогноза выше
# порога дольше этого окна — считаем ситуацию нормализовавшейся и закрываем кейс сами
# (упрощение MVP: без подтверждения фактического ремонта). При окне 48ч на конец бэкфилла
# остаётся ~14 открытых кейсов насос/вентилятор и ~158 дым/газ — управляемо для одного
# диспетчера, остальное честно остаётся в истории как решённое автоматически.
AUTO_CLOSE_AFTER_HOURS = 48


@dataclass(frozen=True)
class Track:
    name: str  # суффикс файлов в docs/analysis/
    category: str  # RiskCase.category / Prediction.category — различает независимые треки в UI
    sensor_types: str  # ModelVersion.sensor_types, через запятую
    threshold: float  # лучшая точка по episode_evaluation_*.json, см. model_report_*.md, раздел 3
    train_period_end: dt.datetime


TRACKS = [
    Track(
        name="насос_вентилятор",
        category="sensor_failure_pump_fan",
        sensor_types="Состояние насоса,Состояние вентилятора",
        threshold=0.55,  # 14.9% episode recall, 2.18 FP/100 устройств/сутки — лучшая проверенная точка
        train_period_end=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    ),
    Track(
        name="дым_газ",
        category="sensor_failure_smoke_gas",
        sensor_types="Датчик дыма,Газовый датчик",
        threshold=0.53,  # 18.5% episode recall при умеренном FP-бюджете — см. model_report_дым_газ.md, раздел 3
        train_period_end=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    ),
]


def import_objects(con: duckdb.DuckDBPyConnection, db) -> dict[int, int]:
    print("importing objects...", file=sys.stderr)
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
    return id_map


def import_channels(con: duckdb.DuckDBPyConnection, db, object_id_map: dict[int, int]) -> dict[int, int]:
    print("importing channels...", file=sys.stderr)
    type_list_sql = ", ".join(f"'{t}'" for t in CORE_TYPES)
    rows = con.execute(
        f"""
        SELECT ид_канала_данных, тип_инж_системы, тип_датчика, тег_инженерной_системы,
               название_датчика, ид_объект,
               regexp_replace(тег_инженерной_системы, '\\d+\\.$', '') AS location_group
        FROM read_csv_auto('{DATASET_DIR / "справочник_каналов_датчиков.csv"}', header=true)
        WHERE тип_датчика IN ({type_list_sql})
        """
    ).fetchall()

    mapping: dict[int, int] = {}
    batch = []
    n_linked = 0
    for ext_id, subsystem, sensor_type, tag, name, ext_object_id, group in rows:
        object_id = object_id_map.get(ext_object_id) if ext_object_id is not None else None
        if object_id is not None:
            n_linked += 1
        batch.append(
            dict(
                external_channel_id=ext_id,
                sensor_type=sensor_type,
                subsystem=subsystem,
                location_tag=tag,
                location_group=group,
                display_name=name,
                object_id=object_id,
            )
        )
    db.bulk_insert_mappings(Channel, batch)
    db.commit()
    for ch in db.query(Channel.id, Channel.external_channel_id).all():
        mapping[ch.external_channel_id] = ch.id
    print(f"  {len(mapping)} channels imported, {n_linked} linked to an object", file=sys.stderr)
    return mapping


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


def load_extra_metrics(track: Track, report: dict) -> dict:
    """feature_importance — уже посчитан при обучении (report), просто раньше не долетал
    до БД/UI. calibration — reliability diagram на test-сплите (scripts/compute_calibration.py),
    отдельная проверка: совпадает ли предсказанная вероятность с реально наблюдаемой частотой
    отказов, а не только ранжирование (ROC-AUC)."""
    extra: dict = {"feature_importance": report["catboost"].get("feature_importance")}
    calibration_path = ANALYSIS_DIR / f"calibration_{track.name}.json"
    if calibration_path.exists():
        extra["calibration"] = json.loads(calibration_path.read_text())
    return extra


def import_model_version(track: Track, db) -> int:
    print(f"[{track.name}] importing model version...", file=sys.stderr)
    report = json.loads((ANALYSIS_DIR / f"model_report_{track.name}.json").read_text())
    mv = ModelVersion(
        name=f"catboost_{track.name}_v1",
        sensor_types=track.sensor_types,
        trained_at=dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc),
        train_period_start=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        train_period_end=track.train_period_end,
        threshold=track.threshold,
        metrics={
            "roc_auc_test": report["catboost"].get("roc_auc_test"),
            "pr_auc_test": report["catboost"].get("pr_auc_test"),
            "target_precision": report["target_precision"],
            "target_recall": report["target_recall"],
            "target_met": False,
            "operating_threshold_note": (
                f"Порог {track.threshold} выбран по лучшей точке эпизодной оценки "
                f"(episode_evaluation_{track.name}.json), не по целевым Precision>0.7/Recall>0.5 — "
                "тема 3 CSV с ответами организаторов подтверждает, что это плановые, не жёсткие "
                "требования, порог можно снижать при обосновании."
            ),
            **load_extra_metrics(track, report),
        },
        artifact_path=f"docs/analysis/catboost_{track.name}.cbm",
        is_active=True,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    print(f"  model_version id={mv.id}", file=sys.stderr)
    return mv.id


def import_risk_cases_and_predictions(track: Track, channel_map: dict[int, int], model_version_id: int, db) -> None:
    print(f"[{track.name}] building alert runs at threshold {track.threshold} (test split only)...", file=sys.stderr)
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE VIEW s AS
        SELECT * FROM read_parquet('{ANALYSIS_DIR / f"scored_{track.name}.parquet"}')
        WHERE split = 'test'
        """
    )
    con.execute(f"CREATE VIEW alerts AS SELECT *, (score >= {track.threshold}) AS is_alert FROM s")
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
                category=track.category,
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
                category=track.category,
                probability=float(score),
                window_start=ts,
                window_end=window_end,
                threshold_used=track.threshold,
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
    print(f"  [{track.name}] {n_risk_cases} risk cases, {len(run_members)} predictions imported", file=sys.stderr)


def close_stale_risk_cases(track: Track, db) -> None:
    """Автозакрытие открытых риск-кейсов трека без новых прогнозов дольше
    AUTO_CLOSE_AFTER_HOURS относительно последнего прогноза этого трека в бэкфилле (см.
    комментарий к константе выше)."""
    result = db.execute(
        text(
            """
            WITH last_pred AS (
                SELECT risk_case_id, max(created_at) AS last_ts
                FROM predictions
                WHERE category = :category
                GROUP BY risk_case_id
            ), track_end AS (
                SELECT max(created_at) AS end_ts FROM predictions WHERE category = :category
            )
            UPDATE risk_cases
            SET status = 'resolved', closed_at = last_pred.last_ts
            FROM last_pred, track_end
            WHERE risk_cases.id = last_pred.risk_case_id
              AND risk_cases.category = :category
              AND risk_cases.status = 'new'
              AND last_pred.last_ts < track_end.end_ts - make_interval(hours => :hours)
            """
        ),
        {"category": track.category, "hours": AUTO_CLOSE_AFTER_HOURS},
    )
    db.commit()
    print(f"  [{track.name}] auto-closed {result.rowcount} stale risk cases", file=sys.stderr)


def main() -> None:
    db = SessionLocal()
    con = duckdb.connect()
    try:
        object_id_map = import_objects(con, db)
        channel_map = import_channels(con, db, object_id_map)
        import_episodes(channel_map, db)
        for track in TRACKS:
            model_version_id = import_model_version(track, db)
            import_risk_cases_and_predictions(track, channel_map, model_version_id, db)
            close_stale_risk_cases(track, db)
        print("DONE", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
