import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { api } from "../api/client";
import type { PredictionOut } from "../api/types";
import { useApi } from "../api/useApi";
import { usePagedApi } from "../api/usePagedApi";
import { AnomalyBadge } from "../components/AnomalyBadge";
import { Badge } from "../components/Badge";
import { SECONDARY_CONTROL, SECONDARY_FIELD } from "../components/controlStyles";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import { ChevronIcon } from "../components/icons";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import { getAnomaly, ShapExplanation } from "../components/ShapExplanation";
import { SortableTh } from "../components/SortableTh";

type SortKey = "created_at" | "probability";
type SortDir = "asc" | "desc";

// «Устаревшее» состояние: последний прогноз старше окна прогноза (24ч) — раздел 2 ТЗ.
// Отсчитывается от САМОГО СВЕЖЕГО известного прогноза в выборке, а не от реальных часов
// браузера — данные replay/бэкфилла всегда датированы прошлым (тестовый период 2025-2026),
// иначе абсолютно все строки всегда выглядели бы «устаревшими».
const STALE_AFTER_HOURS = 24;

export function JournalPage() {
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchError, setSearchError] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selected, setSelected] = useState<PredictionOut | null>(null);

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
    20
  );

  const latestKnown = useMemo(() => {
    const data = predictions.data ?? [];
    if (!data.length) return Date.now();
    return Math.max(...data.map((p) => new Date(p.created_at).getTime()));
  }, [predictions.data]);

  // Всегда что-то выбрано, если в выборке есть хоть одна строка — та же логика, что на
  // «Рисках»: при первой загрузке и после смены фильтра/сортировки берём первую строку;
  // если выбранная запись осталась в выборке, не сбрасываем выбор.
  useEffect(() => {
    if (!predictions.data) return;
    const stillPresent = selected && predictions.data.find((p) => p.id === selected.id);
    if (stillPresent) {
      if (stillPresent !== selected) setSelected(stillPresent);
      return;
    }
    setSelected(predictions.data[0] ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
            Последний прогноз по каждому риск-кейсу — нажмите на строку, чтобы увидеть объяснение модели
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

      <div className="flex flex-col items-start gap-6 lg:flex-row">
        <div className="min-w-0 w-full flex-1">
          <DataState
            loading={predictions.loading}
            error={predictions.error}
            empty={!predictions.data?.length}
            emptyText="Прогнозов ещё нет — модель либо не запускалась, либо все каналы в норме"
          >
            <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                    <SortableTh className='px-2 ps-4 py-3 whitespace-nowrap' label="Время расчёта" sortKey="created_at" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                    <th className="px-2 py-3">Канал</th>
                    <th className="px-2 py-3">Направление</th>
                    <SortableTh label="Вероятность" sortKey="probability" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                    <th className="px-2 py-3">Качество данных</th>
                    <th className="px-2 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {predictions.data?.map((p) => {
                    const ageHours = (latestKnown - new Date(p.created_at).getTime()) / 3600_000;
                    const stale = ageHours > STALE_AFTER_HOURS;
                    return (
                      <tr
                        key={p.id}
                        onClick={() => setSelected(p)}
                        className={`cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 ${
                          p.id === selected?.id ? "bg-sky-100 hover:bg-sky-100" : stale ? "bg-amber-50/40" : ""
                        }`}
                      >
                        <td className="px-2 ps-4 py-3 text-slate-500">
                          {new Date(p.created_at).toLocaleString("ru-RU")}
                        </td>
                        <td className="px-2 py-3 font-medium text-slate-900">
                          <Link
                            to={`/registry?channel_id=${p.channel_external_id ?? p.channel_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sky-700 hover:underline"
                            title="Открыть канал в «Объекты и каналы»"
                          >
                            {p.channel_external_id ?? p.channel_id}
                          </Link>
                          {p.channel_label && p.channel_label !== String(p.channel_external_id) && (
                            <div className="text-sm font-normal text-slate-500">{p.channel_label}</div>
                          )}
                        </td>
                        <td className="px-2 py-3">
                          <Badge tone={categoryTone(p.category)}>{categoryLabel(p.category)}</Badge>
                        </td>
                        <td className="px-2 py-3 font-semibold text-slate-900">
                          {(p.probability * 100).toFixed(1)}%
                        </td>
                        <td className="px-2 py-3">
                          <span className={stale ? "font-medium text-amber-700" : "text-slate-500"}>
                            {p.data_quality_flag ?? "ok"}
                            {stale && " · устарел"}
                          </span>
                        </td>
                        <td className="px-2 py-3 text-slate-400">
                          <ChevronIcon className="h-5 w-5" strokeWidth={2.6} />
                        </td>
                      </tr>
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

        <div className="w-full shrink-0 lg:w-120">
          {selected ? (
            <PredictionDetail prediction={selected} />
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <p className="text-sm text-slate-500">Выберите прогноз в таблице слева, чтобы увидеть объяснение модели</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PredictionDetail({ prediction }: { prediction: PredictionOut }) {
  const anomaly = getAnomaly(prediction.explanation);
  // Лениво по конкретному прогнозу, а не для всех сразу: считается один раз при первом
  // открытии, результат кешируется на backend (Prediction.llm_summary).
  const summary = useApi<{ summary: string | null } | null>(
    () => api.get(`/predictions/${prediction.id}/summary`),
    [prediction.id]
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-y-2 px-1">
        <h3 className="font-display text-base font-semibold text-slate-900">Прогноз #{prediction.id}</h3>
        <Badge tone={categoryTone(prediction.category)}>{categoryLabel(prediction.category)}</Badge>
      </div>

      <DetailSection
        title="Данные"
        right={
          prediction.risk_case_id != null && (
            <Link
              to={`/risks?risk_case_id=${prediction.risk_case_id}`}
              className={`flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-semibold ${SECONDARY_CONTROL}`}
            >
              Открыть риск-кейс
              <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
            </Link>
          )
        }
      >
        <div className="flex items-center justify-between gap-x-2">
          <span className="text-sm text-slate-500">Канал</span>
          <span className="text-sm font-medium text-slate-700">
            {prediction.channel_label ?? prediction.channel_external_id ?? prediction.channel_id}
          </span>
        </div>
        <div className="flex items-center justify-between gap-x-2">
          <span className="text-sm text-slate-500">Время расчёта</span>
          <span className="text-sm font-medium text-slate-700">
            {new Date(prediction.created_at).toLocaleString("ru-RU")}
          </span>
        </div>
        <div className="flex items-center justify-between gap-x-2">
          <span className="text-sm text-slate-500">Окно прогноза</span>
          <span className="text-sm font-medium text-slate-700">
            {new Date(prediction.window_start).toLocaleTimeString("ru-RU")}–
            {new Date(prediction.window_end).toLocaleTimeString("ru-RU")}
          </span>
        </div>
        <div className="flex items-center justify-between gap-x-2">
          <span className="text-sm text-slate-500">Качество данных</span>
          <span className="text-sm font-medium text-slate-700">{prediction.data_quality_flag ?? "ok"}</span>
        </div>
      </DetailSection>

      <DetailSection title="Аналитика" right={anomaly && <AnomalyBadge isOutlier={anomaly.is_outlier} />}>
        <div className="flex items-center justify-between gap-x-2">
          <span className="text-sm text-slate-500">Вероятность отказа</span>
          <span className="text-sm font-semibold text-slate-900">{(prediction.probability * 100).toFixed(1)}%</span>
        </div>
        {summary.loading ? (
          <p className="text-sm text-slate-400 italic">Формируется краткое резюме…</p>
        ) : summary.data?.summary ? (
          <p className="border-b border-slate-100 pb-3 text-sm text-slate-700 italic">{summary.data.summary}</p>
        ) : null}
        <ShapExplanation explanation={prediction.explanation} showAnomaly={false} />
      </DetailSection>
    </div>
  );
}
