import { Link } from "react-router-dom";
import { CATEGORY_LABELS, categoryForSensorTypes, categoryTone } from "../api/categories";
import { api } from "../api/client";
import { REQUEST_STATUS_LABELS, REQUEST_STATUS_TONE } from "../api/requestStatus";
import type { DashboardSummary, MaintenanceRequestStatus } from "../api/types";
import { useApi } from "../api/useApi";
import { Badge, TONE_DOT_CLASSES } from "../components/Badge";
import { BarList } from "../components/BarList";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import { StatTile } from "../components/StatTile";
import { AlertTriangleIcon, CheckCircleIcon, ChevronIcon, FileEditIcon, ListIcon, SparkleIcon } from "../components/icons";

/** Ссылка в шапке карточки «Обзора» — переход в соответствующий раздел, при наличии с
 * готовым фильтром в query (см. DetailSection.right). */
function SectionLink({ to, children }: { to: string; children: string }) {
  return (
    <Link
      to={to}
      className="flex shrink-0 items-center gap-1 text-sm font-medium text-sky-700 hover:underline"
    >
      {children}
      <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
    </Link>
  );
}

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
              <StatTile
                label="Открытые риски"
                value={summary.data.risk_cases.total_open}
                tone="warning"
                icon={<AlertTriangleIcon className="h-5 w-5 text-amber-600" />}
                to="/risks?status=open"
              />
              <StatTile
                label="Новые риски"
                value={summary.data.risk_cases.by_status.new ?? 0}
                tone="track-a"
                icon={<SparkleIcon className="h-5 w-5 text-sky-600" />}
                to="/risks?status=new"
              />
              <StatTile
                label="Всего рисков"
                value={summary.data.risk_cases.total}
                tone="neutral"
                icon={<ListIcon className="h-5 w-5 text-slate-500" />}
                to="/risks"
              />
              <StatTile
                label="Решённые риски"
                value={summary.data.risk_cases.by_status.resolved ?? 0}
                tone="good"
                icon={<CheckCircleIcon className="h-5 w-5 text-emerald-600" />}
                to="/risks?status=resolved"
              />
              <StatTile
                label="Заявки в работе"
                value={summary.data.requests.by_status.draft ?? 0}
                tone="neutral"
                icon={<FileEditIcon className="h-5 w-5 text-slate-500" />}
                to="/requests?status=draft"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <DetailSection title="Риск-кейсы по направлениям" right={<SectionLink to="/risks">Все риски</SectionLink>}>
                <BarList
                  items={Object.entries(CATEGORY_LABELS).map(([key, label]) => ({
                    key,
                    label,
                    value: summary.data!.risk_cases.by_category[key] ?? 0,
                    colorClass: TONE_DOT_CLASSES[categoryTone(key)],
                  }))}
                />
                <div className="space-y-1 border-t border-slate-100 pt-3 text-sm text-slate-500">
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
              </DetailSection>

              <DetailSection
                title="Открытые риски по приоритету"
                right={<SectionLink to="/risks?status=open">Открытые риски</SectionLink>}
              >
                <BarList
                  items={[
                    {
                      key: "high",
                      label: "Критично",
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
              </DetailSection>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <DetailSection title="Заявки по статусу" right={<SectionLink to="/requests">Все заявки</SectionLink>}>
                <BarList
                  items={Object.entries(summary.data.requests.by_status).map(([status, count]) => ({
                    key: status,
                    label: REQUEST_STATUS_LABELS[status as MaintenanceRequestStatus] ?? status,
                    value: count,
                    colorClass: TONE_DOT_CLASSES[REQUEST_STATUS_TONE[status as MaintenanceRequestStatus] ?? "neutral"],
                  }))}
                  emptyText="Заявок нет"
                />
              </DetailSection>

              <DetailSection title="Топ объектов по риску" right={<SectionLink to="/risks">Все риски</SectionLink>}>
                <BarList
                  items={summary.data.top_objects.map((o) => ({
                    key: String(o.object_id),
                    label: o.name,
                    value: o.open_risk_count,
                    to: `/risks?object_id=${o.object_id}`,
                  }))}
                  emptyText="Открытых рисков нет"
                />
              </DetailSection>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <DetailSection
                title="Каналы с растущей частотой сбоев"
                right={<SectionLink to="/registry">Реестр каналов</SectionLink>}
              >
                <p className="text-sm text-slate-500">
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
                    to: c.external_channel_id != null ? `/risks?channel_id=${c.external_channel_id}` : undefined,
                  }))}
                  emptyText="Растущих трендов сейчас нет"
                />
              </DetailSection>

              <DetailSection
                title="Качество моделей (ROC-AUC на test)"
                right={<SectionLink to="/models">Все модели</SectionLink>}
              >
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
                <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-3">
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
              </DetailSection>
            </div>
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
