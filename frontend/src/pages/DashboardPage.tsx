import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryForSensorTypes, categoryTone } from "../api/categories";
import { REQUEST_STATUS_LABELS, REQUEST_STATUS_TONE } from "../api/requestStatus";
import { Badge, TONE_DOT_CLASSES } from "../components/Badge";
import { BarList } from "../components/BarList";
import { DataState } from "../components/DataState";
import { LineChart } from "../components/LineChart";
import { StatTile } from "../components/StatTile";
import type { DashboardSummary, MaintenanceRequestStatus } from "../api/types";

export function DashboardPage() {
  const summary = useApi<DashboardSummary>(() => api.get("/dashboard/summary"), []);

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Обзор</h1>
          <p className="mt-1 text-sm text-slate-500">Состояние системы по обоим направлениям прогнозирования</p>
        </div>
        {summary.data?.worker && <WorkerStatus worker={summary.data.worker} />}
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
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Риск-кейсы по направлениям</h2>
                <BarList
                  items={Object.entries(CATEGORY_LABELS).map(([key, label]) => ({
                    key,
                    label,
                    value: summary.data!.risk_cases.by_category[key] ?? 0,
                    colorClass: TONE_DOT_CLASSES[categoryTone(key)],
                  }))}
                />
                <div className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-sm text-slate-500">
                  {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span>{label} · последний прогноз</span>
                      <span className="font-medium text-slate-700">
                        {summary.data!.last_prediction_by_category[key]
                          ? new Date(summary.data!.last_prediction_by_category[key]).toLocaleString("ru-RU")
                          : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Открытые риски по приоритету</h2>
                <BarList
                  items={[
                    {
                      key: "high",
                      label: "Высокий",
                      value: summary.data.risk_cases.open_by_priority.high ?? 0,
                      colorClass: TONE_DOT_CLASSES.critical,
                    },
                    {
                      key: "medium",
                      label: "Средний",
                      value: summary.data.risk_cases.open_by_priority.medium ?? 0,
                      colorClass: TONE_DOT_CLASSES.warning,
                    },
                  ]}
                  emptyText="Открытых рисков нет"
                />
              </section>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Заявки по статусу</h2>
                <BarList
                  items={Object.entries(summary.data.requests.by_status).map(([status, count]) => ({
                    key: status,
                    label: REQUEST_STATUS_LABELS[status as MaintenanceRequestStatus] ?? status,
                    value: count,
                    colorClass: TONE_DOT_CLASSES[REQUEST_STATUS_TONE[status as MaintenanceRequestStatus] ?? "neutral"],
                  }))}
                  emptyText="Заявок нет"
                />
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Топ объектов по риску</h2>
                <BarList
                  items={summary.data.top_objects.map((o) => ({
                    key: String(o.object_id),
                    label: o.name,
                    value: o.open_risk_count,
                  }))}
                  emptyText="Открытых рисков нет"
                />
              </section>
            </div>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-1 font-display text-sm font-semibold text-slate-900">
                Каналы с растущей частотой сбоев
              </h2>
              <p className="mb-4 text-sm text-slate-500">
                Динамика частоты эпизодов неисправности за последние 90 дней против предыдущих
                90 — не прогноз износа оборудования (данных о возрасте/дате установки нет), а
                наблюдаемый факт по уже собранной истории.
              </p>
              <BarList
                items={(summary.data.top_worsening_channels ?? []).map((c) => ({
                  key: String(c.channel_id),
                  label: c.label,
                  value: c.recent_count,
                  colorClass: TONE_DOT_CLASSES.warning,
                }))}
                emptyText="Растущих трендов сейчас нет"
              />
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-1 font-display text-sm font-semibold text-slate-900">
                Риск-кейсы: открыто / закрыто по дням
              </h2>
              <p className="mb-4 text-sm text-slate-500">
                Закрытие идёт наравне с открытием — очередь не растёт бесконтрольно благодаря
                автозакрытию неактивных случаев
              </p>
              {summary.data.daily_volume.length > 0 ? (
                <LineChart
                  dates={summary.data.daily_volume.map((d) => d.date)}
                  series={[
                    { label: "Открыто", color: "#fab219", values: summary.data.daily_volume.map((d) => d.opened) },
                    { label: "Закрыто", color: "#0ca30c", values: summary.data.daily_volume.map((d) => d.closed) },
                  ]}
                />
              ) : (
                <p className="text-sm text-slate-400">Недостаточно данных</p>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-4 font-display text-sm font-semibold text-slate-900">Качество моделей (ROC-AUC на test)</h2>
              <BarList
                items={summary.data.models.map((m) => {
                  const category = categoryForSensorTypes(m.sensor_types);
                  return {
                    key: String(m.id),
                    label: CATEGORY_LABELS[category],
                    value: m.roc_auc_test ?? 0,
                    colorClass: TONE_DOT_CLASSES[categoryTone(category)],
                  };
                })}
                formatValue={(v) => v.toFixed(2)}
              />
              <div className="mt-4 flex flex-wrap gap-3 border-t border-slate-100 pt-3">
                {summary.data.models.map((m) => (
                  <div key={m.id} className="flex items-center gap-2 text-sm text-slate-500">
                    <span className="font-medium text-slate-700">{m.name}</span>
                    <span>порог {m.threshold?.toFixed(2)}</span>
                    <Badge tone={m.target_met ? "good" : "warning"}>
                      {m.target_met ? "Цель достигнута" : "Ниже плановой цели"}
                    </Badge>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </DataState>
    </div>
  );
}

function WorkerStatus({ worker }: { worker: NonNullable<DashboardSummary["worker"]> }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium ${
        worker.is_stale ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"
      }`}
      title={`Виртуальное время воркера: ${new Date(worker.virtual_time).toLocaleString("ru-RU")}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${worker.is_stale ? "bg-red-500" : "bg-emerald-500 animate-pulse"}`} />
      {worker.is_stale
        ? `Воркер не отвечает уже ${Math.round(worker.seconds_since_update / 60)} мин`
        : `Воркер тикает · ${worker.seconds_since_update} сек назад`}
    </div>
  );
}
