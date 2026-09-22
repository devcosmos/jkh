"""Проставляет реальное SHAP-объяснение и независимый сигнал аномальности (IsolationForest)
на последний прогноз каждого риск-кейса (любого статуса, включая закрытые/отклонённые —
изначально (20 сентября) покрывались только открытые: RiskCard.tsx на тот момент запрашивал
"последний прогноз по каналу", где для закрытых кейсов заглушка была не так заметна. После
исправления RiskCard.tsx на честный `risk_case_id`-фильтр (21 сентября, docs/documentation/Технические_заметки.md)
неполный backfill стал видимым пробелом: закрытые кейсы показывали "Объяснение недоступно"
вместо реального SHAP, хотя признаки для их прогнозов физически есть в тех же parquet-файлах,
что и для открытых. Ограничение на статус снято — расхождение источника было только в охвате
запроса, не в доступности данных).

Массовый импорт (import_analysis_to_db.py) не хранил признаки построчно — только
итоговый score из scored_<track>.parquet, поэтому исторические прогнозы получили общую
заглушку в explanation. Точный вектор признаков, использованный моделью, лежит в
features_<track>_2024_2026.parquet по тому же (channel_id=внешний id, ts), что и в
scored_<track>.parquet. Дальше — тот же `explain_prediction`, что и в живом воркере, чтобы
объяснение считалось одной и той же моделью и логикой в обоих путях.

Запуск: JKH_DATABASE_URL=... python3 scripts/maintenance/backfill_shap_explanations.py
"""
import sys
from pathlib import Path

import duckdb
import joblib
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import Prediction  # noqa: E402
from app.workers.replay_worker import (  # noqa: E402
    ALL_FEATURES,
    TRACKS,
    compute_anomaly_signal,
    explain_prediction,
)
from catboost import CatBoostClassifier  # noqa: E402


def latest_prediction_ids(db, category: str) -> list[tuple[int, int, int]]:
    """-> [(prediction_id, external_channel_id, ts_epoch), ...] для каждого риск-кейса этой
    категории (любого статуса) — последний по времени прогноз, привязанный именно к нему
    (`p.risk_case_id = rc.id`), не последний прогноз по каналу вообще."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (rc.id) p.id, c.external_channel_id, p.created_at
            FROM risk_cases rc
            JOIN predictions p ON p.risk_case_id = rc.id
            JOIN channels c ON c.id = rc.channel_id
            WHERE rc.category = :category
            ORDER BY rc.id, p.created_at DESC
            """
        ),
        {"category": category},
    ).all()
    return [(pid, ext_id, ts) for pid, ext_id, ts in rows]


def main() -> None:
    db = SessionLocal()
    con = duckdb.connect()
    total_updated = 0
    total_missing = 0
    try:
        for track in TRACKS:
            targets = latest_prediction_ids(db, track.category)
            if not targets:
                print(f"[{track.name}] нет открытых риск-кейсов", file=sys.stderr)
                continue

            model = CatBoostClassifier()
            model.load_model(str(ARTIFACTS_DIR / f"catboost_{track.name}.cbm"))
            anomaly_bundle = joblib.load(ARTIFACTS_DIR / f"isolation_forest_{track.name}.joblib")

            lookup_df = con.execute(
                "SELECT * FROM (VALUES " + ",".join(f"({pid}, {ext_id}, TIMESTAMP '{ts}')" for pid, ext_id, ts in targets) + ") AS t(prediction_id, channel_id, ts)"
            ).df()
            con.register("targets", lookup_df)
            matched = con.execute(
                f"""
                SELECT t.prediction_id, f.* EXCLUDE (channel_id, ts, y_true, future_fully_observed, in_fault_now)
                FROM targets t
                JOIN read_parquet('{ARTIFACTS_DIR / f"features_{track.name}_2024_2026.parquet"}') f
                  ON f.channel_id = t.channel_id AND f.ts = t.ts
                """
            ).df()

            found_ids = set(matched["prediction_id"])
            missing = len(targets) - len(found_ids)
            total_missing += missing
            if missing:
                print(f"[{track.name}] нет строки признаков для {missing} из {len(targets)}", file=sys.stderr)

            for _, r in matched.iterrows():
                features = {
                    "n_alarms_1h": r["n_alarms_1h"],
                    "n_alarms_24h": r["n_alarms_24h"],
                    "n_alarms_7d": r["n_alarms_7d"],
                    "n_transitions_1h": r["n_transitions_1h"],
                    "n_transitions_24h": r["n_transitions_24h"],
                    "n_transitions_7d": r["n_transitions_7d"],
                    "n_events_1h": r["n_events_1h"],
                    "n_events_24h": r["n_events_24h"],
                    "n_events_7d": r["n_events_7d"],
                    "seconds_since_last_event": r["seconds_since_last_event"],
                    "n_neighbors_in_fault": r["n_neighbors_in_fault"],
                    "frac_neighbors_in_fault": r["n_neighbors_in_fault"] / max(r["n_neighbors_total"], 1),
                    "current_state": r["current_state"],
                    "тип_датчика": r["тип_датчика"],
                }
                row = [[features[f] for f in ALL_FEATURES]]
                explanation = {
                    **explain_prediction(model, row),
                    "anomaly": compute_anomaly_signal(anomaly_bundle, features),
                }
                pred = db.get(Prediction, int(r["prediction_id"]))
                pred.explanation = explanation
                total_updated += 1

            db.commit()
            print(f"[{track.name}] обновлено объяснений: {len(found_ids)}", file=sys.stderr)
    finally:
        db.close()

    print(f"итого обновлено: {total_updated}, без совпадения признаков: {total_missing}")


if __name__ == "__main__":
    main()
