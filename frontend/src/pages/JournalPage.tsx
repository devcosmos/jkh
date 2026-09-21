import { Fragment, useMemo, useState } from "react";
import { usePagedApi } from "../api/usePagedApi";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { Badge } from "../components/Badge";
import { DataState } from "../components/DataState";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import { ShapExplanation } from "../components/ShapExplanation";
import type { PredictionOut } from "../api/types";

// «Устаревшее» состояние: последний прогноз старше окна прогноза (24ч) — раздел 2 ТЗ.
// Отсчитывается от САМОГО СВЕЖЕГО известного прогноза в выборке, а не от реальных часов
// браузера — данные replay/бэкфилла всегда датированы прошлым (тестовый период 2025-2026),
// иначе абсолютно все строки всегда выглядели бы «устаревшими».
const STALE_AFTER_HOURS = 24;

export function JournalPage() {
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const predictions = usePagedApi<PredictionOut>(
    (limit, offset) =>
      `/predictions?limit=${limit}&offset=${offset}${categoryFilter ? `&category=${categoryFilter}` : ""}`,
    [categoryFilter],
    50
  );

  const latestKnown = useMemo(() => {
    const data = predictions.data ?? [];
    if (!data.length) return Date.now();
    return Math.max(...data.map((p) => new Date(p.created_at).getTime()));
  }, [predictions.data]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Журнал прогнозов</h1>
          <p className="mt-1 text-sm text-slate-500">Сохранённые прогнозы модели с историей и версией</p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="">Оба направления</option>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
          <button
            onClick={predictions.reload}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900"
          >
            Обновить
          </button>
        </div>
      </div>

      <DataState
        loading={predictions.loading}
        error={predictions.error}
        empty={!predictions.data?.length}
        emptyText="Прогнозов ещё нет — модель либо не запускалась, либо все каналы в норме"
      >
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Время расчёта</th>
                <th className="px-4 py-3">Канал</th>
                <th className="px-4 py-3">Направление</th>
                <th className="px-4 py-3">Вероятность</th>
                <th className="px-4 py-3">Окно</th>
                <th className="px-4 py-3">Качество данных</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {predictions.data?.map((p) => {
                const ageHours = (latestKnown - new Date(p.created_at).getTime()) / 3600_000;
                const stale = ageHours > STALE_AFTER_HOURS;
                const expanded = expandedId === p.id;
                return (
                  <Fragment key={p.id}>
                    <tr
                      onClick={() => setExpandedId(expanded ? null : p.id)}
                      className={`cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50 ${stale ? "bg-amber-50/40" : ""}`}
                    >
                      <td className="px-4 py-3 text-slate-500">
                        {new Date(p.created_at).toLocaleString("ru-RU")}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">{p.channel_id}</td>
                      <td className="px-4 py-3">
                        <Badge tone={categoryTone(p.category)}>{categoryLabel(p.category)}</Badge>
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900">
                        {(p.probability * 100).toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-slate-500">
                        {new Date(p.window_start).toLocaleTimeString("ru-RU")}–
                        {new Date(p.window_end).toLocaleTimeString("ru-RU")}
                      </td>
                      <td className="px-4 py-3">
                        <span className={stale ? "font-medium text-amber-700" : "text-slate-500"}>
                          {p.data_quality_flag ?? "ok"}
                          {stale && " · устарел"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400">{expanded ? "▲" : "▼"}</td>
                    </tr>
                    {expanded && (
                      <tr className="border-b border-slate-100 bg-slate-50/60 last:border-0">
                        <td colSpan={7} className="px-4 py-4">
                          <ShapExplanation explanation={p.explanation} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          <Pagination
            page={predictions.page}
            pageSize={predictions.pageSize}
            total={predictions.total}
            loadedCount={predictions.data?.length ?? 0}
            onPageChange={predictions.setPage}
          />
        </div>
      </DataState>
    </div>
  );
}
