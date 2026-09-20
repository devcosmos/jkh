import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { Badge } from "../components/Badge";
import { DataState } from "../components/DataState";
import { StatTile } from "../components/StatTile";
import type { DashboardSummary } from "../api/types";

export function DashboardPage() {
  const summary = useApi<DashboardSummary>(() => api.get("/dashboard/summary"), []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Обзор</h1>
        <p className="mt-1 text-sm text-slate-500">Состояние системы по обоим направлениям прогнозирования</p>
      </div>

      <DataState loading={summary.loading} error={summary.error} empty={!summary.data} emptyText="Нет данных">
        {summary.data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <StatTile label="Открытых рисков" value={summary.data.risk_cases.total_open} tone="warning" />
              <StatTile
                label="Критичных"
                value={summary.data.risk_cases.open_by_priority.high ?? 0}
                tone="critical"
              />
              <StatTile
                label="Аномалий (независимая модель)"
                value={summary.data.risk_cases.open_with_anomaly}
                tone="serious"
              />
              <StatTile
                label="Черновиков заявок"
                value={summary.data.requests.by_status.draft ?? 0}
                tone="neutral"
              />
              <StatTile label="Активных версий модели" value={summary.data.models.length} tone="track-a" />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">По направлениям</h2>
                <div className="space-y-3">
                  {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between text-sm">
                      <Badge tone={categoryTone(key)}>{label}</Badge>
                      <div className="flex items-center gap-4 text-slate-500">
                        <span>
                          риск-кейсов: <b className="text-slate-900">{summary.data!.risk_cases.by_category[key] ?? 0}</b>
                        </span>
                        <span>
                          посл. прогноз:{" "}
                          <b className="text-slate-900">
                            {summary.data!.last_prediction_by_category[key]
                              ? new Date(summary.data!.last_prediction_by_category[key]).toLocaleString("ru-RU")
                              : "—"}
                          </b>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Заявки по статусу</h2>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(summary.data.requests.by_status).map(([status, count]) => (
                    <Badge key={status} tone="neutral">
                      {status}: {count}
                    </Badge>
                  ))}
                  {Object.keys(summary.data.requests.by_status).length === 0 && (
                    <span className="text-sm text-slate-400">Заявок нет</span>
                  )}
                </div>
              </section>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Топ объектов по риску</h2>
                {summary.data.top_objects.length === 0 ? (
                  <p className="text-sm text-slate-400">Открытых рисков нет</p>
                ) : (
                  <ul className="space-y-2">
                    {summary.data.top_objects.map((o) => (
                      <li key={o.object_id} className="flex items-center justify-between text-sm">
                        <span className="text-slate-700">{o.name}</span>
                        <Badge tone="warning">{o.open_risk_count}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Активные модели</h2>
                <div className="space-y-3">
                  {summary.data.models.map((m) => (
                    <div key={m.id} className="flex items-center justify-between text-sm">
                      <div>
                        <div className="font-medium text-slate-900">{m.name}</div>
                        <div className="text-xs text-slate-500">
                          порог {m.threshold?.toFixed(2)} · ROC-AUC{" "}
                          {m.roc_auc_test != null ? m.roc_auc_test.toFixed(2) : "—"}
                        </div>
                      </div>
                      <Badge tone={m.target_met ? "good" : "warning"}>
                        {m.target_met ? "Цель достигнута" : "Ниже плановой цели"}
                      </Badge>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        )}
      </DataState>
    </div>
  );
}
