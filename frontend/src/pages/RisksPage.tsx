import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryLabel, categoryTone } from "../api/categories";
import { RISK_STATUS_LABELS, RISK_STATUS_TONE } from "../api/riskStatus";
import { Badge, riskPriorityTone } from "../components/Badge";
import { DataState } from "../components/DataState";
import { ObjectsTree } from "../components/ObjectsTree";
import { Select } from "../components/Select";
import { StatTile } from "../components/StatTile";
import { RiskCard } from "./RiskCard";
import type { ObjectsTreeResponse, RiskCaseOut } from "../api/types";

export function RisksPage() {
  const [view, setView] = useState<"list" | "scheme">("list");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [selected, setSelected] = useState<RiskCaseOut | null>(null);

  const risks = useApi<RiskCaseOut[]>(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (categoryFilter) params.set("category", categoryFilter);
    const qs = params.toString();
    return api.get(`/risk-cases${qs ? `?${qs}` : ""}`);
  }, [statusFilter, categoryFilter]);
  const tree = useApi<ObjectsTreeResponse>(() => api.get("/objects/tree"), []);

  // После решения диспетчера риск-кейс перезагружается со свежим статусом — без этого
  // карточка справа продолжала бы показывать старый статус, будто решение никуда не делось.
  useEffect(() => {
    if (!selected || !risks.data) return;
    const updated = risks.data.find((r) => r.id === selected.id);
    if (updated && updated !== selected) setSelected(updated);
  }, [risks.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => {
    const data = risks.data ?? [];
    return {
      total: data.length,
      critical: data.filter((r) => r.priority === "high").length,
      warning: data.filter((r) => r.priority === "medium").length,
      fresh: data.filter((r) => r.status === "new").length,
    };
  }, [risks.data]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Риски</h1>
          <p className="mt-1 text-sm text-slate-500">Прогнозы отказов датчиков по обоим направлениям</p>
        </div>
        <button
          onClick={risks.reload}
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900"
        >
          <RefreshIcon className="h-4 w-4" />
          Обновить
        </button>
      </div>

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

      <div className="flex items-start gap-6">
        <div className="min-w-0 flex-1">
          {view === "list" ? (
            <DataState
              loading={risks.loading}
              error={risks.error}
              empty={!risks.data?.length}
              emptyText="Активных рисков нет"
            >
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">Канал</th>
                      <th className="px-4 py-3">Направление</th>
                      <th className="px-4 py-3">Статус</th>
                      <th className="px-4 py-3">Приоритет</th>
                      <th className="px-4 py-3">Открыт</th>
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
                        <td className="px-4 py-3 font-medium text-slate-400">#{r.id}</td>
                        <td className="px-4 py-3 font-medium text-slate-900">{r.channel_id}</td>
                        <td className="px-4 py-3">
                          <Badge tone={categoryTone(r.category)}>{categoryLabel(r.category)}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={RISK_STATUS_TONE[r.status] ?? "neutral"} dot>
                            {RISK_STATUS_LABELS[r.status] ?? r.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          {r.priority ? (
                            <Badge tone={riskPriorityTone(r.priority)}>
                              {r.priority === "high" ? "Высокий" : "Средний"}
                            </Badge>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {new Date(r.opened_at).toLocaleString("ru-RU")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
                  <p className="mt-3 text-xs text-slate-500">
                    Реальные координаты объектов организаторами не предоставляются (только
                    текущие, теряются при демонтаже датчика) — вместо GPS-карты иерархическая
                    схема объектов с цветовой индикацией риска, как рекомендовано организаторами.
                  </p>
                </>
              )}
            </DataState>
          )}
        </div>

        {selected && (
          <div className="w-96 shrink-0">
            <RiskCard key={selected.id} riskCase={selected} onDecided={() => risks.reload()} />
          </div>
        )}
      </div>
    </div>
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
