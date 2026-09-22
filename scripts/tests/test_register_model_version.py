"""build_metrics в scripts/maintenance/register_model_version.py должен разворачивать сырой
model_report_<track>.json в тот же плоский вид, что пишет import_model_version в
scripts/data/import_analysis_to_db.py и что читает frontend/src/pages/ModelsPage.tsx
(roc_auc_test, target_precision, ... верхнего уровня, не вложенный catboost). Раньше
register_model_version.py сохранял --report как есть, и после регистрации новой версии
через этот скрипт показатели на странице «Модели» пропадали.

Запуск: source .venv/bin/activate && python3 -m pytest scripts/tests/ -v
"""
import importlib.util
import json
from pathlib import Path

MAINTENANCE_DIR = Path(__file__).resolve().parent.parent / "maintenance"


def _load_module():
    spec = importlib.util.spec_from_file_location("register_model_version", MAINTENANCE_DIR / "register_model_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT = {
    "target_precision": 0.42,
    "target_recall": 0.11,
    "catboost": {
        "roc_auc_test": 0.91,
        "pr_auc_test": 0.33,
        "feature_importance": {"n_alarms_24h": 12.5},
    },
}


def test_build_metrics_flattens_nested_catboost_report(tmp_path):
    mod = _load_module()
    report_path = tmp_path / "model_report_насос_вентилятор.json"
    report_path.write_text(json.dumps(REPORT), encoding="utf-8")
    args = mod.parse_args(
        [
            "--track", "насос_вентилятор",
            "--threshold", "0.55",
            "--train-start", "2024-01-01",
            "--train-end", "2025-01-01",
            "--report", str(report_path),
        ]
    )

    metrics = mod.build_metrics(args, REPORT)

    assert metrics["roc_auc_test"] == 0.91
    assert metrics["pr_auc_test"] == 0.33
    assert metrics["target_precision"] == 0.42
    assert metrics["target_recall"] == 0.11
    assert metrics["feature_importance"] == {"n_alarms_24h": 12.5}
    assert "0.55" in metrics["operating_threshold_note"]
    assert "calibration" not in metrics


def test_build_metrics_includes_calibration_when_present(tmp_path):
    mod = _load_module()
    report_path = tmp_path / "model_report_насос_вентилятор.json"
    report_path.write_text(json.dumps(REPORT), encoding="utf-8")
    calibration = [{"bin_start": 0.5, "bin_end": 0.6, "n": 10, "mean_predicted": 0.55, "observed_rate": 0.5, "reliable": True}]
    (tmp_path / "calibration_насос_вентилятор.json").write_text(json.dumps(calibration), encoding="utf-8")
    args = mod.parse_args(
        [
            "--track", "насос_вентилятор",
            "--threshold", "0.55",
            "--train-start", "2024-01-01",
            "--train-end", "2025-01-01",
            "--report", str(report_path),
        ]
    )

    metrics = mod.build_metrics(args, REPORT)

    assert metrics["calibration"] == calibration
