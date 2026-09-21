import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryForSensorTypes, categoryTone } from "../api/categories";
import { REQUEST_STATUS_LABELS, REQUEST_STATUS_TONE } from "../api/requestStatus";
import { Badge, TONE_DOT_CLASSES } from "../components/Badge";
import { BarList } from "../components/BarList";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
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
              <DetailSection title="Риск-кейсы по направлениям">
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

              <DetailSection title="Открытые риски по приоритету">
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
              </DetailSection>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <DetailSection title="Заявки по статусу">
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

              <DetailSection title="Топ объектов по риску">
                <BarList
                  items={summary.data.top_objects.map((o) => ({
                    key: String(o.object_id),
                    label: o.name,
                    value: o.open_risk_count,
                  }))}
                  emptyText="Открытых рисков нет"
                />
              </DetailSection>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <DetailSection title="Каналы с растущей частотой сбоев">
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
                  }))}
                  emptyText="Растущих трендов сейчас нет"
                />
              </DetailSection>

              <DetailSection title="Качество моделей (ROC-AUC на test)">
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

            <DailyVolumeSection dailyVolume={summary.data.daily_volume} />
          </div>
        )}
      </DataState>
    </div>
  );
}

type VolumeTabKey = "opened" | "closed";

const VOLUME_TABS: { key: VolumeTabKey; label: string; color: string; growthIsGood: boolean }[] = [
  { key: "opened", label: "Открыто", color: "#fab219", growthIsGood: false },
  { key: "closed", label: "Закрыто", color: "#0ca30c", growthIsGood: true },
];

function volumeStats(values: number[]) {
  const total = values.reduce((sum, v) => sum + v, 0);
  const avgPerDay = values.length ? total / values.length : 0;
  let trendPct: number | null = null;
  if (values.length >= 4) {
    const mid = Math.floor(values.length / 2);
    const firstAvg = values.slice(0, mid).reduce((s, v) => s + v, 0) / mid;
    const secondAvg = values.slice(mid).reduce((s, v) => s + v, 0) / (values.length - mid);
    trendPct = firstAvg > 0 ? ((secondAvg - firstAvg) / firstAvg) * 100 : secondAvg > 0 ? 100 : 0;
  }
  return { total, avgPerDay, trendPct };
}

/** Карточка «area chart + вкладки с разбивкой» (в духе Preline area-chart-card-with-tabbed-breakdown):
 * график с обеими сериями всегда виден целиком, вкладки переключают только сводку под ним —
 * без сторонних чарт-библиотек, на уже имеющемся LineChart (area=true). */
function DailyVolumeSection({ dailyVolume }: { dailyVolume: DashboardSummary["daily_volume"] }) {
  const [tab, setTab] = useState<VolumeTabKey>("opened");
  const active = VOLUME_TABS.find((t) => t.key === tab)!;
  const totalChanges = useMemo(
    () => dailyVolume.reduce((sum, d) => sum + d.opened + d.closed, 0),
    [dailyVolume]
  );
  const stats = useMemo(
    () => volumeStats(dailyVolume.map((d) => d[tab])),
    [dailyVolume, tab]
  );

  return (
    <DetailSection title="Риск-кейсы: открыто / закрыто по дням">
      <p className="text-sm text-slate-500">
        Закрытие идёт наравне с открытием — очередь не растёт бесконтрольно благодаря
        автозакрытию неактивных случаев
      </p>

      {dailyVolume.length > 0 ? (
        <>
          <div>
            <div className="text-2xl font-medium text-slate-900">{totalChanges.toLocaleString("ru-RU")}</div>
            <div className="text-sm text-slate-500">изменений статуса риск-кейсов за период</div>
          </div>

          <LineChart
            dates={dailyVolume.map((d) => d.date)}
            series={VOLUME_TABS.map((t) => ({ label: t.label, color: t.color, values: dailyVolume.map((d) => d[t.key]) }))}
            area
            legend={false}
            height={180}
          />

          <div className="flex gap-1 border-t border-slate-100 pt-3">
            {VOLUME_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === t.key ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                <span className="size-2.5 rounded-xs" style={{ background: t.color }} />
                {t.label}
              </button>
            ))}
          </div>

          <div className="divide-y divide-slate-100">
            <VolumeRow label="Всего за период" value={stats.total.toLocaleString("ru-RU")} />
            <VolumeRow label="В среднем за день" value={stats.avgPerDay.toFixed(1)} />
            <VolumeRow
              label="Тренд ко второй половине периода"
              value={stats.trendPct == null ? "—" : `${stats.trendPct > 0 ? "+" : ""}${stats.trendPct.toFixed(0)}%`}
              tone={
                stats.trendPct == null || Math.round(stats.trendPct) === 0
                  ? "neutral"
                  : (stats.trendPct > 0) === active.growthIsGood
                    ? "good"
                    : "bad"
              }
            />
          </div>
        </>
      ) : (
        <p className="text-sm text-slate-400">Недостаточно данных</p>
      )}
    </DetailSection>
  );
}

function VolumeRow({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <div className="flex items-center justify-between py-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <span
        className={`font-medium ${
          tone === "good" ? "text-emerald-600" : tone === "bad" ? "text-red-600" : "text-slate-700"
        }`}
      >
        {value}
      </span>
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
