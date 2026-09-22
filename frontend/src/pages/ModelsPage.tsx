import { api, getRole } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge } from "../components/Badge";
import { BarList } from "../components/BarList";
import { CalibrationChart } from "../components/CalibrationChart";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import type { ModelVersionOut } from "../api/types";

const FEATURE_LABELS: Record<string, string> = {
  n_alarms_1h: "Тревог за 1 час",
  n_alarms_24h: "Тревог за 24 часа",
  n_alarms_7d: "Тревог за 7 суток",
  n_transitions_1h: "Переходов состояния за 1 час",
  n_transitions_24h: "Переходов состояния за 24 часа",
  n_transitions_7d: "Переходов состояния за 7 суток",
  n_events_1h: "Событий за 1 час",
  n_events_24h: "Событий за 24 часа",
  n_events_7d: "Событий за 7 суток",
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
  const isAdmin = getRole() === "admin";
  const history = useApi<ModelVersionOut[]>(() => (isAdmin ? api.get("/models") : Promise.resolve([])), [isAdmin]);
  const replacedVersions = history.data?.filter((m) => !m.is_active) ?? [];

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
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
              <DetailSection
                key={m.id}
                title={m.name}
                right={
                  <Badge tone={targetMet ? "good" : "warning"}>
                    {targetMet ? "Плановая цель достигнута" : "Ниже плановой цели (обоснованно)"}
                  </Badge>
                }
                footer={
                  <span className="text-sm text-slate-400">
                    Обучена {new Date(m.trained_at).toLocaleDateString("ru-RU")}
                  </span>
                }
              >
                <p className="text-sm text-slate-500">{m.sensor_types.split(",").join(", ")}</p>

                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Metric label="Рабочий порог" value={m.threshold?.toFixed(2) ?? "—"} />
                  <Metric label="ROC-AUC (test)" value={rocAuc != null ? rocAuc.toFixed(3) : "—"} />
                  <Metric label="PR-AUC (test)" value={prAuc != null ? prAuc.toFixed(3) : "—"} />
                  <Metric
                    label="Плановая цель P/R"
                    value={targetPrecision != null && targetRecall != null ? `${targetPrecision}/${targetRecall}` : "—"}
                  />
                </div>

                {note && <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{note}</p>}

                {(topFeatures.length > 0 || calibration) && (
                  <div className="grid gap-6 border-t border-slate-100 pt-4 lg:grid-cols-2">
                    {topFeatures.length > 0 && (
                      <div>
                        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                          Какие признаки важнее всего для этой модели
                        </h4>
                        <BarList
                          variant="fill"
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
                      <div>
                        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                          Калибровка вероятности (test)
                        </h4>
                        <CalibrationChart bins={calibration} />
                      </div>
                    )}
                  </div>
                )}
              </DetailSection>
            );
          })}
        </div>
      </DataState>

      {isAdmin && replacedVersions.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            История версий (заменённые дообучением)
          </h2>
          <p className="mb-3 text-sm text-slate-400">
            Раздел 8 ЖКХ.md — регистрация новой версии описана в{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5">scripts/maintenance/register_model_version.py</code>
          </p>
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Название</th>
                  <th className="px-4 py-3">Направление</th>
                  <th className="px-4 py-3">Обучена</th>
                  <th className="px-4 py-3">Порог</th>
                </tr>
              </thead>
              <tbody>
                {replacedVersions.map((m) => (
                  <tr key={m.id} className="border-b border-slate-100 text-slate-500 last:border-0">
                    <td className="px-4 py-3">{m.name}</td>
                    <td className="px-4 py-3">{m.sensor_types.split(",").join(", ")}</td>
                    <td className="px-4 py-3">{new Date(m.trained_at).toLocaleDateString("ru-RU")}</td>
                    <td className="px-4 py-3">{m.threshold?.toFixed(2) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-display text-lg font-semibold text-slate-900">{value}</div>
      <div className="mt-0.5 text-sm text-slate-500">{label}</div>
    </div>
  );
}
