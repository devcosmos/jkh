import type { FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../../api/categories";
import { api } from "../../api/client";
import { RISK_STATUS_LABELS, RISK_STATUS_TONE } from "../../api/riskStatus";
import type { ObjectsTreeResponse, ObjectTreeNode, RiskCaseOut } from "../../api/types";
import { useApi } from "../../api/useApi";
import { usePagedApi } from "../../api/usePagedApi";
import { Badge, riskPriorityTone } from "../../components/Badge";
import { BarList } from "../../components/BarList";
import { SECONDARY_CONTROL, SECONDARY_FIELD } from "../../components/controlStyles";
import { DataState } from "../../components/DataState";
import { DetailSection } from "../../components/DetailSection";
import { FilterBanner } from "../../components/FilterBanner";
import { ChevronIcon } from "../../components/icons";
import { countTreeNodes, ObjectsTree, topRiskyNodes } from "../../components/ObjectsTree";
import { Pagination } from "../../components/Pagination";
import { Select } from "../../components/Select";
import { SortableTh } from "../../components/SortableTh";
import { StatTile } from "../../components/StatTile";
import { useEnterAnimation } from "../../components/useEnterAnimation";
import { exportCsv } from "../../lib/exportCsv";
import { RiskCard } from "../../pages/RiskCard";

type SortKey = "probability" | "opened_at" | "id" | "channel" | "category" | "status" | "priority";
type SortDir = "asc" | "desc";

export function RisksPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkRiskCaseId = searchParams.get("risk_case_id");
  const channelFilter = searchParams.get("channel_id");
  const objectFilter = searchParams.get("object_id");
  const [view, setView] = useState<"list" | "scheme">("list");
  // Начальные значения — из query-параметров ссылки (например, с плашек «Обзора»), дальше
  // это уже обычные локальные фильтры страницы, независимые от URL.
  const [statusFilter, setStatusFilter] = useState<string>(() => searchParams.get("status") ?? "");
  const [categoryFilter, setCategoryFilter] = useState<string>(() => searchParams.get("category") ?? "");
  const [priorityFilter, setPriorityFilter] = useState<string>(() => searchParams.get("priority") ?? "");
  const [anomalyFilter, setAnomalyFilter] = useState<boolean>(() => searchParams.get("has_anomaly") === "true");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchError, setSearchError] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("opened_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selected, setSelected] = useState<RiskCaseOut | null>(null);
  const initialSelectionDone = useRef(false);

  const risks = usePagedApi<RiskCaseOut>(
    (limit, offset) => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      if (priorityFilter) params.set("priority", priorityFilter);
      if (anomalyFilter) params.set("has_anomaly", "true");
      if (channelFilter) params.set("channel_id", channelFilter);
      if (objectFilter) params.set("object_id", objectFilter);
      if (searchQuery) params.set("search", searchQuery);
      params.set("sort_by", sortBy);
      params.set("sort_dir", sortDir);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      return `/risk-cases?${params.toString()}`;
    },
    [statusFilter, categoryFilter, priorityFilter, anomalyFilter, channelFilter, objectFilter, searchQuery, sortBy, sortDir],
    20
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
      // Счётчики — по текущей странице, не по всей выборке (та же экономика, что и
      // раньше: без отдельных агрегирующих запросов на каждый статус/приоритет).
      critical: data.filter((r) => r.priority === "high").length,
      warning: data.filter((r) => r.priority === "medium").length,
      fresh: data.filter((r) => r.status === "new").length,
      resolved: data.filter((r) => r.status === "resolved").length,
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
                { header: "% отказа", value: (r) => r.latest_probability != null ? Math.round(r.latest_probability * 100) : "" },
                { header: "Статус", value: (r) => RISK_STATUS_LABELS[r.status] ?? r.status },
                { header: "Приоритет", value: (r) => r.priority ?? "" },
                { header: "Открыт", value: (r) => new Date(r.opened_at).toLocaleString("ru-RU") },
              ])
            }
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${SECONDARY_CONTROL}`}
          >
            <DownloadIcon className="h-4 w-4" />
            Экспорт CSV
          </button>
          <button
            onClick={risks.reload}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium ${SECONDARY_CONTROL}`}
          >
            <RefreshIcon className="h-4 w-4" />
            Обновить
          </button>
        </div>
      </div>

      {channelFilter && (
        <FilterBanner onClear={clearChannelFilter} clearLabel="Показать все риски">
          Показаны риски только по каналу <span className="font-semibold">#{channelFilter}</span>
        </FilterBanner>
      )}

      {objectFilter && (
        <FilterBanner onClear={clearObjectFilter} clearLabel="Показать все риски">
          Показаны риски только по объекту <span className="font-semibold">#{objectFilter}</span>
        </FilterBanner>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Критично" value={stats.critical} tone="critical" />
        <StatTile label="Требуют внимания" value={stats.warning} tone="warning" />
        <StatTile label="Новые" value={stats.fresh} tone="track-a" />
        <StatTile label="Решённые" value={stats.resolved} tone="good" />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex rounded-xl border border-sky-200 bg-sky-50 p-1">
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
        {view === "list" && (
          <>
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
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">Все статусы</option>
              <option value="open">Открытые</option>
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
            <Select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
              <option value="">Любой приоритет</option>
              <option value="high">Критично</option>
              <option value="medium">Средний</option>
            </Select>
            <button
              type="button"
              onClick={() => setAnomalyFilter((v) => !v)}
              aria-pressed={anomalyFilter}
              className={`rounded-xl px-3.5 py-2 text-sm font-medium transition-colors ${
                anomalyFilter ? "bg-orange-100 text-orange-700" : SECONDARY_CONTROL
              }`}
            >
              Только аномалии
            </button>
          </>
        )}
      </div>

      {view === "scheme" ? (
        <DataState loading={tree.loading} error={tree.error} empty={!tree.data?.roots.length} emptyText="Объектов нет">
          {tree.data && <ObjectsSchemeView roots={tree.data.roots} />}
        </DataState>
      ) : (
      <div className="flex flex-col items-start gap-6 lg:flex-row">
        <div className="min-w-0 w-full flex-1">
            <DataState
              loading={risks.loading}
              error={risks.error}
              empty={!risks.data?.length}
              emptyText="Активных рисков нет"
            >
              <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                      <SortableTh
                        label="ID"
                        sortKey="id"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 ps-4 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="ID канала"
                        sortKey="channel"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="Направление"
                        sortKey="category"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="% отказа"
                        sortKey="probability"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="Статус"
                        sortKey="status"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="Приоритет"
                        sortKey="priority"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <SortableTh
                        label="Открыт"
                        sortKey="opened_at"
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        className="px-2 py-3 whitespace-nowrap"
                      />
                      <th className="px-2 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {risks.data?.map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => setSelected(r)}
                        className={`cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 ${
                          r.id === selected?.id ? "bg-sky-100 hover:bg-sky-100" : ""
                        }`}
                      >
                        <td className="px-2 ps-4 py-3 font-medium whitespace-nowrap text-slate-400">#{r.id}</td>
                        <td className="px-2 py-3 font-medium whitespace-nowrap text-slate-900">
                          <Link
                            to={`/registry?channel_id=${r.channel_external_id ?? r.channel_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sky-700 hover:underline"
                            title="Открыть канал в «Объекты и каналы»"
                          >
                            {r.channel_external_id ?? r.channel_id}
                          </Link>
                          {r.channel_label && r.channel_label !== String(r.channel_external_id) && (
                            <div className="text-sm font-normal text-slate-500">{r.channel_label}</div>
                          )}
                        </td>
                        <td className="px-2 py-3 whitespace-nowrap">
                          <Badge tone={categoryTone(r.category)}>{categoryLabel(r.category)}</Badge>
                        </td>
                        <td className="px-2 py-3">
                          <ProbabilityCell probability={r.latest_probability} />
                        </td>
                        <td className="px-2 py-3 whitespace-nowrap">
                          <Badge tone={RISK_STATUS_TONE[r.status] ?? "neutral"} dot>
                            {RISK_STATUS_LABELS[r.status] ?? r.status}
                          </Badge>
                        </td>
                        <td className="px-2 py-3 whitespace-nowrap">
                          {r.priority ? (
                            <Badge tone={riskPriorityTone(r.priority)} icon="priority">
                              {r.priority === "high" ? "Критично" : "Средний"}
                            </Badge>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-2 py-3 whitespace-nowrap text-slate-500">
                          <div>{new Date(r.opened_at).toLocaleDateString("ru-RU")}</div>
                          <div className="text-slate-400">{new Date(r.opened_at).toLocaleTimeString("ru-RU")}</div>
                        </td>
                        <td className="px-2 py-3 text-slate-400">
                          <ChevronIcon className="h-5 w-5" strokeWidth={2.6} />
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
      )}
    </div>
  );
}

// Цвет кольца — от самого показанного числа, а не от сохранённого приоритета риск-кейса:
// приоритет выставляется один раз при открытии кейса и дальше не пересчитывается (см.
// app/workers/replay_worker.py), а вероятность в этой ячейке — самая свежая. Со временем
// они расходятся (кейс открылся на 90% как «высокий», сейчас 82% — приоритет остался
// «высокий»), и кольцо, окрашенное по приоритету, начинало противоречить своему же числу.
function ProbabilityCell({ probability }: { probability: number | null }) {
  const entered = useEnterAnimation();
  if (probability == null) return <span className="text-slate-400">—</span>;
  const pct = Math.round(probability * 100);
  const color = pct >= 85 ? "#d03b3b" : pct >= 50 ? "#fab219" : "#94a3b8";
  const size = 44;
  const stroke = 4;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - (entered ? pct : 0) / 100);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} title={`${pct}% отказа`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#f1f5f9" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-slate-900">{pct}</span>
    </div>
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

// Без списка/риск-кейса и фильтров, на всю ширину страницы — раньше "Схема объектов" делила
// экран с карточкой риска и повторяла фильтры списка, хотя у самого дерева фильтров нет и
// клик по строке ничего не выбирает. Справа — топ объектов по СОБСТВЕННЫМ открытым рискам
// (не по агрегату поддерева, иначе топ всегда состоял бы из самых верхних объектов) и общие
// цифры/легенда — то, что раньше не было видно вообще.
function ObjectsSchemeView({ roots }: { roots: ObjectTreeNode[] }) {
  const { total, withOwnRisk } = countTreeNodes(roots);
  const top = topRiskyNodes(roots);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="min-w-0 lg:col-span-2">
        <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-slate-500">
          <span>
            Объектов: <span className="font-semibold text-slate-800">{total}</span>
          </span>
          <span>
            С открытыми рисками: <span className="font-semibold text-slate-800">{withOwnRisk}</span>
          </span>
          <span className="ml-auto flex items-center gap-4">
            <LegendItem colorClass="bg-[#d03b3b]" label="Критично" />
            <LegendItem colorClass="bg-[#fab219]" label="Средний" />
            <LegendItem colorClass="bg-slate-300" label="Нет открытых" />
          </span>
        </div>
        <ObjectsTree roots={roots} />
        <p className="mt-3 text-sm text-slate-500">
          Реальные координаты объектов организаторами не предоставляются (только текущие,
          теряются при демонтаже датчика) — вместо GPS-карты иерархическая схема объектов с
          цветовой индикацией риска, как рекомендовано организаторами.
        </p>
      </div>

      <DetailSection title="Топ объектов по открытым рискам" className="lg:self-start mt-8">
        <BarList
          items={top.map((n) => ({
            key: String(n.id),
            label: n.name,
            value: n.own_open_risk_count,
            colorClass: n.aggregated_max_priority === "high" ? "bg-[#d03b3b]" : "bg-[#fab219]",
            to: `/risks?object_id=${n.id}`,
          }))}
          emptyText="Открытых рисков нет"
        />
      </DetailSection>
    </div>
  );
}

function LegendItem({ colorClass, label }: { colorClass: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${colorClass}`} />
      {label}
    </span>
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
