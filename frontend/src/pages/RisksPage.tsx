import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { usePagedApi } from "../api/usePagedApi";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { RISK_STATUS_LABELS, RISK_STATUS_TONE } from "../api/riskStatus";
import { Badge, riskPriorityTone } from "../components/Badge";
import { DataState } from "../components/DataState";
import { ObjectsTree } from "../components/ObjectsTree";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import { StatTile } from "../components/StatTile";
import { exportCsv } from "../lib/exportCsv";
import { RiskCard } from "./RiskCard";
import type { ObjectsTreeResponse, RiskCaseOut } from "../api/types";

type SortKey = "probability" | "opened_at";
type SortDir = "asc" | "desc";

export function RisksPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkRiskCaseId = searchParams.get("risk_case_id");
  const channelFilter = searchParams.get("channel_id");
  const objectFilter = searchParams.get("object_id");
  const [view, setView] = useState<"list" | "scheme">("list");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchError, setSearchError] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("probability");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selected, setSelected] = useState<RiskCaseOut | null>(null);
  const initialSelectionDone = useRef(false);

  const risks = usePagedApi<RiskCaseOut>(
    (limit, offset) => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      if (channelFilter) params.set("channel_id", channelFilter);
      if (objectFilter) params.set("object_id", objectFilter);
      if (searchQuery) params.set("search", searchQuery);
      params.set("sort_by", sortBy);
      params.set("sort_dir", sortDir);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      return `/risk-cases?${params.toString()}`;
    },
    [statusFilter, categoryFilter, channelFilter, objectFilter, searchQuery, sortBy, sortDir],
    50
  );
  const tree = useApi<ObjectsTreeResponse>(() => api.get("/objects/tree"), []);

  // Всегда что-то выбрано, если в выборке есть хоть один риск-кейс: при первой загрузке,
  // после смены фильтра/сортировки (когда старый выбор мог выпасть из выборки) — берём первую
  // строку текущей сортировки. Если выбранный кейс остался в выборке, просто обновляем его
  // данными (после решения диспетчера статус должен смениться, а не остаться старым).
  //
  // Сквозная ссылка из «Заявок» (?risk_case_id=) обрабатывается один раз при самой первой
  // загрузке выборки — грузим конкретный риск-кейс напрямую по ID, он может не входить в
  // текущую страницу/фильтр/сортировку списка.
  useEffect(() => {
    if (!risks.data) return;

    if (!initialSelectionDone.current) {
      initialSelectionDone.current = true;
      if (deepLinkRiskCaseId) {
        api
          .get<RiskCaseOut>(`/risk-cases/${deepLinkRiskCaseId}`)
          .then(setSelected)
          .catch(() => setSelected(risks.data![0] ?? null));
        return;
      }
    }

    const stillPresent = selected && risks.data.find((r) => r.id === selected.id);
    if (stillPresent) {
      if (stillPresent !== selected) setSelected(stillPresent);
      return;
    }
    setSelected(risks.data[0] ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [risks.data]);

  const stats = useMemo(() => {
    const data = risks.data ?? [];
    return {
      // Общее число в выборке (все страницы) — из X-Total-Count, не только текущая
      // страница. Остальные счётчики — по текущей странице (та же экономика, что и раньше:
      // без отдельных агрегирующих запросов на каждый статус/приоритет по всей выборке).
      total: risks.total ?? data.length,
      critical: data.filter((r) => r.priority === "high").length,
      warning: data.filter((r) => r.priority === "medium").length,
      fresh: data.filter((r) => r.status === "new").length,
    };
  }, [risks.data, risks.total]);

  function clearChannelFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("channel_id");
    setSearchParams(next);
  }

  function clearObjectFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("object_id");
    setSearchParams(next);
  }

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
          <h1 className="font-display text-2xl font-semibold text-slate-900">Риски</h1>
          <p className="mt-1 text-sm text-slate-500">
            Прогнозы отказов датчиков по обоим направлениям — нажмите на строку, чтобы принять решение
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            disabled={!risks.data?.length}
            onClick={() =>
              exportCsv(`risks_${new Date().toISOString().slice(0, 10)}.csv`, risks.data ?? [], [
                { header: "ID", value: (r) => r.id },
                { header: "ID канала", value: (r) => r.channel_external_id ?? r.channel_id },
                { header: "Название канала", value: (r) => r.channel_label ?? "" },
                { header: "Направление", value: (r) => categoryLabel(r.category) },
                { header: "Вероятность отказа", value: (r) => r.latest_probability ?? "" },
                { header: "Статус", value: (r) => RISK_STATUS_LABELS[r.status] ?? r.status },
                { header: "Приоритет", value: (r) => r.priority ?? "" },
                { header: "Открыт", value: (r) => new Date(r.opened_at).toLocaleString("ru-RU") },
              ])
            }
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <DownloadIcon className="h-4 w-4" />
            Экспорт CSV
          </button>
          <button
            onClick={risks.reload}
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900"
          >
            <RefreshIcon className="h-4 w-4" />
            Обновить
          </button>
        </div>
      </div>

      {channelFilter && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-sky-50 px-4 py-2.5 text-sm text-sky-800">
          <span>
            Показаны риски только по каналу <span className="font-semibold">#{channelFilter}</span>
          </span>
          <button onClick={clearChannelFilter} className="font-medium text-sky-700 hover:text-sky-900">
            Показать все риски ×
          </button>
        </div>
      )}

      {objectFilter && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-sky-50 px-4 py-2.5 text-sm text-sky-800">
          <span>
            Показаны риски только по объекту <span className="font-semibold">#{objectFilter}</span>
          </span>
          <button onClick={clearObjectFilter} className="font-medium text-sky-700 hover:text-sky-900">
            Показать все риски ×
          </button>
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Всего в выборке" value={stats.total} tone="neutral" />
        <StatTile label="Критично" value={stats.critical} tone="critical" />
        <StatTile label="Требуют внимания" value={stats.warning} tone="warning" />
        <StatTile label="Новые" value={stats.fresh} tone="track-a" />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
          <button
            className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
              view === "list" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
            }`}
            onClick={() => setView("list")}
          >
            Список
          </button>
          <button
            className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
              view === "scheme" ? "bg-slate-900 text-white" : "text-slate-500 hover:text-slate-900"
            }`}
            onClick={() => setView("scheme")}
          >
            Схема объектов
          </button>
        </div>
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
              className={`w-56 rounded-xl border px-3.5 py-2 text-sm text-slate-900 outline-none focus:ring-4 ${
                searchError
                  ? "border-red-300 focus:border-red-400 focus:ring-red-100"
                  : "border-slate-200 focus:border-sky-400 focus:ring-sky-100"
              }`}
            />
            {searchError && <span className="mt-1 text-sm text-red-600">Введите число</span>}
          </div>
          {searchQuery ? (
            <button
              type="button"
              onClick={clearSearch}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-500 hover:text-slate-900"
            >
              ×
            </button>
          ) : (
            <button
              type="submit"
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:border-slate-300 hover:text-slate-900"
            >
              Найти
            </button>
          )}
        </form>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {Object.entries(RISK_STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">Оба направления</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-col items-start gap-6 lg:flex-row">
        <div className="min-w-0 w-full flex-1">
          {view === "list" ? (
            <DataState
              loading={risks.loading}
              error={risks.error}
              empty={!risks.data?.length}
              emptyText="Активных рисков нет"
            >
              <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-3 whitespace-nowrap">ID</th>
                      <th className="px-4 py-3 whitespace-nowrap">ID канала</th>
                      <th className="px-4 py-3 whitespace-nowrap">Направление</th>
                      <SortableTh label="Вероятность отказа" sortKey="probability" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                      <th className="px-4 py-3 whitespace-nowrap">Статус</th>
                      <th className="px-4 py-3 whitespace-nowrap">Приоритет</th>
                      <SortableTh label="Открыт" sortKey="opened_at" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {risks.data?.map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => setSelected(r)}
                        className={`cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 ${
                          r.id === selected?.id ? "bg-sky-50/70 hover:bg-sky-50/70" : ""
                        }`}
                      >
                        <td className="px-4 py-3 font-medium whitespace-nowrap text-slate-400">#{r.id}</td>
                        <td className="px-4 py-3 font-medium whitespace-nowrap text-slate-900">
                          <div>{r.channel_external_id ?? r.channel_id}</div>
                          {r.channel_label && r.channel_label !== String(r.channel_external_id) && (
                            <div className="text-sm font-normal text-slate-500">{r.channel_label}</div>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Badge tone={categoryTone(r.category)}>{categoryLabel(r.category)}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <ProbabilityCell probability={r.latest_probability} tone={riskPriorityTone(r.priority)} />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Badge tone={RISK_STATUS_TONE[r.status] ?? "neutral"} dot>
                            {RISK_STATUS_LABELS[r.status] ?? r.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {r.priority ? (
                            <Badge tone={riskPriorityTone(r.priority)}>
                              {r.priority === "high" ? "Высокий" : "Средний"}
                            </Badge>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                          {new Date(r.opened_at).toLocaleString("ru-RU")}
                        </td>
                        <td className="px-4 py-3 text-slate-300">
                          <ChevronIcon className="h-4 w-4" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination
                  page={risks.page}
                  pageSize={risks.pageSize}
                  total={risks.total}
                  loadedCount={risks.data?.length ?? 0}
                  onPageChange={risks.setPage}
                />
              </div>
            </DataState>
          ) : (
            <DataState
              loading={tree.loading}
              error={tree.error}
              empty={!tree.data?.roots.length}
              emptyText="Объектов нет"
            >
              {tree.data && (
                <>
                  <ObjectsTree roots={tree.data.roots} />
                  <p className="mt-3 text-sm text-slate-500">
                    Реальные координаты объектов организаторами не предоставляются (только
                    текущие, теряются при демонтаже датчика) — вместо GPS-карты иерархическая
                    схема объектов с цветовой индикацией риска, как рекомендовано организаторами.
                  </p>
                </>
              )}
            </DataState>
          )}
        </div>

        <div className="w-full shrink-0 lg:w-120">
          {selected ? (
            <RiskCard key={selected.id} riskCase={selected} onDecided={() => risks.reload()} />
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <PointerIcon className="h-8 w-8 text-slate-300" />
              <p className="text-sm text-slate-500">
                Выберите риск-кейс в таблице слева, чтобы увидеть, почему сработал прогноз, и принять решение
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ProbabilityCell({ probability, tone }: { probability: number | null; tone: ReturnType<typeof riskPriorityTone> }) {
  if (probability == null) return <span className="text-slate-400">—</span>;
  const pct = Math.round(probability * 100);
  const barColor = tone === "critical" ? "bg-[#d03b3b]" : tone === "warning" ? "bg-[#fab219]" : "bg-slate-400";
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-10 shrink-0 font-semibold text-slate-900">{pct}%</span>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-1.5 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SortableTh({
  label,
  sortKey,
  sortBy,
  sortDir,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sortBy: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sortBy === sortKey;
  return (
    <th className="px-4 py-3 whitespace-nowrap">
      <button
        onClick={() => onSort(sortKey)}
        className={`flex items-center gap-1 uppercase tracking-wide transition-colors ${
          active ? "text-slate-900" : "text-slate-500 hover:text-slate-700"
        }`}
      >
        {label}
        <span className={`text-[10px] ${active ? "opacity-100" : "opacity-30"}`}>{sortDir === "desc" ? "▼" : "▲"}</span>
      </button>
    </th>
  );
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M12 4v11m0 0 4-4m-4 4-4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 18.5v.5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M20 11A8 8 0 1 0 6.3 17.7M20 11V5M20 11h-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="m9 6 6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PointerIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M6 3.5 18 12l-5.2 1.3L11 19 6 3.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
