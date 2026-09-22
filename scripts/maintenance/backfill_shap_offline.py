"""Считает SHAP-объяснения ЛОКАЛЬНО (без подключения к прод-БД) для набора прогнозов,
выгруженного с прода заранее, и генерирует один SQL-файл с UPDATE-выражениями — применяется
на проде отдельной командой через `docker exec -i ... psql -f -` (см. docs/documentation/Технические_заметки.md,
запись 21 сентября — "локальные вычисления, потом дамп на прод", не живой SSH-туннель).

Вход: CSV без заголовка, колонки category,prediction_id,external_channel_id,created_at —
получен на проде через `docker exec jkh-db-1 psql ... -c "SELECT ..."` (см. команду в сессии).

Запуск:
    python3 scripts/maintenance/backfill_shap_offline.py /tmp/backfill_targets_recent.csv > /tmp/backfill.sql
"""
import csv
import json
import sys
from pathlib import Path

import duckdb
import joblib

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.explain import compute_anomaly_signal, explain_prediction  # noqa: E402
from app.ml.features import ALL_FEATURES  # noqa: E402
from app.ml.models import TRACKS  # noqa: E402
from catboost import CatBoostClassifier  # noqa: E402


def sql_literal(explanation: dict) -> str:
    return json.dumps(explanation, ensure_ascii=False).replace("'", "''")


def main() -> None:
    csv_path = Path(sys.argv[1])
    rows_by_category: dict[str, list[tuple[int, int, str]]] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for category, pred_id, ext_channel_id, created_at in csv.reader(f):
            rows_by_category.setdefault(category, []).append((int(pred_id), int(ext_channel_id), created_at))

    con = duckdb.connect()
    total_updated = 0
    total_missing = 0

    print("BEGIN;")
    for track in TRACKS:
        targets = rows_by_category.get(track.category, [])
        if not targets:
            print(f"-- [{track.name}] нет целей в выгрузке", file=sys.stderr)
            continue

        model = CatBoostClassifier()
        model.load_model(str(ARTIFACTS_DIR / f"catboost_{track.name}.cbm"))
        anomaly_bundle = joblib.load(ARTIFACTS_DIR / f"isolation_forest_{track.name}.joblib")

        values = ",".join(f"({pid}, {ext_id}, TIMESTAMP '{ts}')" for pid, ext_id, ts in targets)
        lookup_df = con.execute(f"SELECT * FROM (VALUES {values}) AS t(prediction_id, channel_id, ts)").df()
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
            print(f"-- [{track.name}] нет строки признаков для {missing} из {len(targets)}", file=sys.stderr)

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
            print(
                f"UPDATE predictions SET explanation = '{sql_literal(explanation)}'::jsonb "
                f"WHERE id = {int(r['prediction_id'])};"
            )
            total_updated += 1

        print(f"-- [{track.name}] обновлено объяснений: {len(found_ids)}", file=sys.stderr)

    print("COMMIT;")
    print(f"-- итого обновлено: {total_updated}, без совпадения признаков: {total_missing}", file=sys.stderr)


if __name__ == "__main__":
    main()
