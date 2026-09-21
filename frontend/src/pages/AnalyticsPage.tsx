import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DataState } from "../components/DataState";
import { StatTile } from "../components/StatTile";
import type { AnalyticsReport } from "../api/types";

const MAINTENANCE_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  approved: "Утверждена",
  in_progress: "В работе",
  completed: "Завершена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

/** Раздел 8 ЖКХ.md («Дополнительные требования», по согласованию с заказчиком, не
 * блокирует MVP): детальная статистика по типам инцидентов, сезонная аналитика,
 * исторические отчёты по ремонтам, экспорт в PDF/XLSX для руководства. */
export function AnalyticsPage() {
  const report = useApi<AnalyticsReport>(() => api.get("/analytics/summary"), []);
  const [downloading, setDownloading] = useState<"xlsx" | "pdf" | null>(null);

  async function download(format: "xlsx" | "pdf") {
    setDownloading(format);
    try {
      await api.downloadFile(`/analytics/report.${format}`, `jkh_analytics_report.${format}`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Аналитика</h1>
          <p className="mt-1 text-sm text-slate-500">
            Типы инцидентов, сезонность, исторический отчёт по заявкам на обслуживание
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            disabled={downloading !== null}
            onClick={() => download("xlsx")}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {downloading === "xlsx" ? "Формируется…" : "Скачать XLSX"}
          </button>
          <button
            disabled={downloading !== null}
            onClick={() => download("pdf")}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {downloading === "pdf" ? "Формируется…" : "Скачать PDF"}
          </button>
        </div>
      </div>

      <DataState loading={report.loading} error={report.error} empty={false}>
        {report.data && (
          <div className="space-y-8">
            <IncidentTypesSection data={report.data.incident_types} />
            <SeasonalSection data={report.data.seasonal} />
            <MaintenanceSection data={report.data.maintenance} />
          </div>
        )}
      </DataState>
    </div>
  );
}

function IncidentTypesSection({ data }: { data: AnalyticsReport["incident_types"] }) {
  const maxEpisodes = Math.max(...data.map((r) => r.episode_count), 1);
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Детальная статистика по типам инцидентов
      </h2>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Тип датчика</th>
              <th className="px-4 py-3">Эпизодов (реальных)</th>
              <th className="px-4 py-3">Риск-кейсов</th>
              <th className="px-4 py-3">Открыто сейчас</th>
              <th className="px-4 py-3">Ср. вероятность (открытые)</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.sensor_type} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-900">{row.sensor_type}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-28 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-2 rounded-full bg-sky-500"
                        style={{ width: `${(row.episode_count / maxEpisodes) * 100}%` }}
                      />
                    </div>
                    <span className="text-slate-600">{row.episode_count.toLocaleString("ru-RU")}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-600">{row.risk_case_count.toLocaleString("ru-RU")}</td>
                <td className="px-4 py-3 text-slate-600">{row.open_risk_case_count}</td>
                <td className="px-4 py-3 text-slate-600">
                  {row.avg_open_probability != null ? `${Math.round(row.avg_open_probability * 100)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SeasonalSection({ data }: { data: AnalyticsReport["seasonal"] }) {
  const max = Math.max(...data.map((r) => r.episode_count), 1);
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Сезонность — эпизоды неисправности по месяцам (все годы данных)
      </h2>
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-end gap-2" style={{ height: "160px" }}>
          {data.map((row) => (
            <div key={row.month} className="group relative flex flex-1 flex-col items-center justify-end gap-1.5">
              <span className="text-[11px] font-medium text-slate-500 opacity-0 transition-opacity group-hover:opacity-100">
                {row.episode_count.toLocaleString("ru-RU")}
              </span>
              <div
                className="w-full rounded-t-md bg-sky-500 transition-colors group-hover:bg-sky-600"
                style={{ height: `${Math.max((row.episode_count / max) * 130, 2)}px` }}
                title={`${row.month_name}: ${row.episode_count} эпизодов`}
              />
              <span className="text-[11px] text-slate-500">{row.month_name.slice(0, 3)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function MaintenanceSection({ data }: { data: AnalyticsReport["maintenance"] }) {
  const maxWorkType = Math.max(...data.by_work_type.map((r) => r.count), 1);
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Исторический отчёт по заявкам на обслуживание
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">По виду работ</h3>
          <div className="space-y-2.5">
            {data.by_work_type.map((row) => (
              <div key={row.work_type}>
                <div className="mb-1 flex items-baseline justify-between text-sm">
                  <span className="text-slate-700">{row.work_type}</span>
                  <span className="font-medium text-slate-500">{row.count}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-violet-500"
                    style={{ width: `${(row.count / maxWorkType) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {data.by_work_type.length === 0 && <p className="text-sm text-slate-400">Заявок нет</p>}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">По статусу</h3>
          <div className="flex flex-wrap gap-2">
            {data.by_status.map((row) => (
              <span
                key={row.status}
                className="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700"
              >
                {MAINTENANCE_STATUS_LABELS[row.status] ?? row.status}: {row.count}
              </span>
            ))}
          </div>
          {data.avg_hours_to_approval != null && (
            <div className="mt-4">
              <StatTile
                label="Среднее время до утверждения"
                value={`${data.avg_hours_to_approval.toLocaleString("ru-RU")} ч`}
                tone="track-a"
              />
            </div>
          )}
        </div>
      </div>

      {data.monthly.length > 0 && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Заявки по месяцам
          </h3>
          <div className="flex flex-wrap gap-3 text-sm text-slate-600">
            {data.monthly.map((row) => (
              <span key={row.month} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                {row.month}: <span className="font-medium text-slate-900">{row.request_count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
