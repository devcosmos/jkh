import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge } from "../components/Badge";
import { BarList } from "../components/BarList";
import { CalibrationChart } from "../components/CalibrationChart";
import { DataState } from "../components/DataState";
import type { ModelVersionOut } from "../api/types";

const FEATURE_LABELS: Record<string, string> = {
  n_alarms_1h: "Тревог за 1ч",
  n_alarms_24h: "Тревог за 24ч",
  n_alarms_7d: "Тревог за 7сут",
  n_transitions_1h: "Переходов состояния за 1ч",
  n_transitions_24h: "Переходов состояния за 24ч",
  n_transitions_7d: "Переходов состояния за 7сут",
  n_events_1h: "Событий за 1ч",
  n_events_24h: "Событий за 24ч",
  n_events_7d: "Событий за 7сут",
  seconds_since_last_event: "Секунд с последнего события",
  n_neighbors_in_fault: "Соседей в отказе",
  frac_neighbors_in_fault: "Доля соседей в отказе",
  current_state: "Текущее состояние",
  тип_датчика: "Тип датчика",
};

function metricNumber(metrics: Record<string, unknown> | null, key: string): number | null {
  const v = metrics?.[key];
  return typeof v === "number" ? v : null;
}

export function ModelsPage() {
  const models = useApi<ModelVersionOut[]>(() => api.get("/models/current"), []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Модели</h1>
        <p className="mt-1 text-sm text-slate-500">
          Активные версии CatBoost — по одной на независимо оцениваемое направление
        </p>
      </div>

      <DataState loading={models.loading} error={models.error} empty={!models.data?.length} emptyText="Активных моделей нет">
        <div className="space-y-4">
          {models.data?.map((m) => {
            const rocAuc = metricNumber(m.metrics, "roc_auc_test");
            const prAuc = metricNumber(m.metrics, "pr_auc_test");
            const targetPrecision = metricNumber(m.metrics, "target_precision");
            const targetRecall = metricNumber(m.metrics, "target_recall");
            const targetMet = m.metrics?.target_met === true;
            const note = typeof m.metrics?.operating_threshold_note === "string" ? m.metrics.operating_threshold_note : null;
            const featureImportance = m.metrics?.feature_importance as Record<string, number> | undefined;
            const calibration = m.metrics?.calibration as
              | { bin_start: number; bin_end: number; n: number; mean_predicted: number | null; observed_rate: number | null; reliable: boolean }[]
              | undefined;
            const topFeatures = featureImportance
              ? Object.entries(featureImportance)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 5)
              : [];

            return (
              <div key={m.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-display text-base font-semibold text-slate-900">{m.name}</h3>
                    <p className="mt-1 text-sm text-slate-500">{m.sensor_types}</p>
                  </div>
                  <Badge tone={targetMet ? "good" : "warning"}>
                    {targetMet ? "Плановая цель достигнута" : "Ниже плановой цели (обоснованно)"}
                  </Badge>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Metric label="Рабочий порог" value={m.threshold?.toFixed(2) ?? "—"} />
                  <Metric label="ROC-AUC (test)" value={rocAuc != null ? rocAuc.toFixed(3) : "—"} />
                  <Metric label="PR-AUC (test)" value={prAuc != null ? prAuc.toFixed(3) : "—"} />
                  <Metric
                    label="Плановая цель P/R"
                    value={targetPrecision != null && targetRecall != null ? `${targetPrecision}/${targetRecall}` : "—"}
                  />
                </div>

                <div className="mt-3 text-xs text-slate-400">
                  Обучена {new Date(m.trained_at).toLocaleDateString("ru-RU")}
                </div>

                {note && <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-500">{note}</p>}

                {topFeatures.length > 0 && (
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Какие признаки важнее всего для этой модели
                    </h4>
                    <BarList
                      items={topFeatures.map(([key, value]) => ({
                        key,
                        label: FEATURE_LABELS[key] ?? key,
                        value,
                      }))}
                      formatValue={(v) => v.toFixed(1)}
                    />
                  </div>
                )}

                {calibration && (
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Калибровка вероятности (test)
                    </h4>
                    <CalibrationChart bins={calibration} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </DataState>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-display text-lg font-semibold text-slate-900">{value}</div>
      <div className="mt-0.5 text-xs text-slate-500">{label}</div>
    </div>
  );
}
