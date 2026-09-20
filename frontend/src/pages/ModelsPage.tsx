import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge } from "../components/Badge";
import { DataState } from "../components/DataState";
import type { ModelVersionOut } from "../api/types";

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
