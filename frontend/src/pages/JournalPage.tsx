import { Fragment, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { usePagedApi } from "../api/usePagedApi";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { Badge } from "../components/Badge";
import { SECONDARY_CONTROL, SECONDARY_FIELD } from "../components/controlStyles";
import { DataState } from "../components/DataState";
import { SortableTh } from "../components/SortableTh";
import { ChevronIcon } from "../components/icons";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import { ShapExplanation } from "../components/ShapExplanation";
import type { PredictionOut } from "../api/types";

// «Устаревшее» состояние: последний прогноз старше окна прогноза (24ч) — раздел 2 ТЗ.
// Отсчитывается от САМОГО СВЕЖЕГО известного прогноза в выборке, а не от реальных часов
// браузера — данные replay/бэкфилла всегда датированы прошлым (тестовый период 2025-2026),
// иначе абсолютно все строки всегда выглядели бы «устаревшими».
const STALE_AFTER_HOURS = 24;

type SortKey = "created_at" | "probability";
type SortDir = "asc" | "desc";

export function JournalPage() {
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchError, setSearchError] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const predictions = usePagedApi<PredictionOut>(
    // latest_per_case — один (последний) прогноз на риск-кейс, а не сырой поток всех
    // почасовых тиков: реальный SHAP посчитан backfill'ом только для последнего прогноза
    // каждого кейса (той же выборки, что открывает RiskCard.tsx), без этого фильтра журнал
    // в основном показывал старые тики с технической заглушкой вместо объяснения.
    (limit, offset) => {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      params.set("latest_per_case", "true");
      if (categoryFilter) params.set("category", categoryFilter);
      if (searchQuery) params.set("search", searchQuery);
      params.set("sort_by", sortBy);
      params.set("sort_dir", sortDir);
      return `/predictions?${params.toString()}`;
    },
    [categoryFilter, searchQuery, sortBy, sortDir],
    50
  );

  const latestKnown = useMemo(() => {
    const data = predictions.data ?? [];
    if (!data.length) return Date.now();
    return Math.max(...data.map((p) => new Date(p.created_at).getTime()));
  }, [predictions.data]);

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    const trimmed = searchInput.trim();
    if (trimmed && !/^\d+$/.test(trimmed)) {
      setSearchError(true);
      return;
    }
    setSearchError(false);
    setSearchQuery(trimmed);
  }

  function clearSearch() {
    setSearchInput("");
    setSearchQuery("");
    setSearchError(false);
  }

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  }

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Журнал прогнозов</h1>
          <p className="mt-1 text-sm text-slate-500">
            Последний прогноз по каждому риск-кейсу, с объяснением модели
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <form onSubmit={submitSearch} className="flex items-center gap-1.5">
            <div className="flex flex-col">
              <input
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  setSearchError(false);
                }}
                placeholder="Поиск по ID риска или канала…"
                inputMode="numeric"
                className={`w-56 rounded-xl px-3.5 py-2 text-sm ${
                  searchError
                    ? "border border-red-300 bg-red-50 text-slate-900 outline-none focus:border-red-400 focus:bg-white focus:ring-4 focus:ring-red-100"
                    : SECONDARY_FIELD
                }`}
              />
              {searchError && <span className="mt-1 text-sm text-red-600">Введите число</span>}
            </div>
            {searchQuery ? (
              <button
                type="button"
                onClick={clearSearch}
                className={`rounded-xl px-3 py-2 text-sm font-medium ${SECONDARY_CONTROL}`}
              >
                ×
              </button>
            ) : (
              <button type="submit" className={`rounded-xl px-3 py-2 text-sm font-medium ${SECONDARY_CONTROL}`}>
                Найти
              </button>
            )}
          </form>
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
            className={`rounded-xl px-3.5 py-2 text-sm font-medium ${SECONDARY_CONTROL}`}
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
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                <SortableTh label="Время расчёта" sortKey="created_at" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                <th className="px-4 py-3">Канал</th>
                <th className="px-4 py-3">Направление</th>
                <SortableTh label="Вероятность" sortKey="probability" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                <th className="px-4 py-3">Окно</th>
                <th className="px-4 py-3">Качество данных</th>
                <th className="px-4 py-3" />
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
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {p.channel_external_id ?? p.channel_id}
                        {p.channel_label && p.channel_label !== String(p.channel_external_id) && (
                          <div className="text-sm font-normal text-slate-500">{p.channel_label}</div>
                        )}
                      </td>
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
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        {p.risk_case_id != null && (
                          <Link
                            to={`/risks?risk_case_id=${p.risk_case_id}`}
                            className={`flex w-fit shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-semibold ${SECONDARY_CONTROL}`}
                          >
                            Риск
                            <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
                          </Link>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-400">
                        <ChevronIcon
                          className={`h-4 w-4 transition-transform ${expanded ? "-rotate-90" : "rotate-90"}`}
                          strokeWidth={2}
                        />
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-b border-slate-100 bg-slate-50/60 last:border-0">
                        <td colSpan={8} className="px-4 py-4">
                          <PredictionSummary predictionId={p.id} />
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

// Резюме ИИ по прогнозу — дублирует то же поле, что карточка риска (Prediction.llm_summary),
// подгружается лениво только для развёрнутой строки, чтобы список журнала не дёргал LLM
// на каждую строку сразу при открытии страницы.
function PredictionSummary({ predictionId }: { predictionId: number }) {
  const summary = useApi<{ summary: string | null } | null>(
    () => api.get(`/predictions/${predictionId}/summary`),
    [predictionId]
  );
  if (summary.loading) {
    return <p className="mb-3 text-sm text-slate-400 italic">Формируется краткое резюме…</p>;
  }
  if (!summary.data?.summary) return null;
  return (
    <p className="mb-3 border-b border-slate-200 pb-3 text-sm text-slate-700 italic">
      {summary.data.summary}
    </p>
  );
}
