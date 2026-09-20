import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { CATEGORY_LABELS, categoryLabel } from "../api/categories";
import { DataState } from "../components/DataState";
import { ObjectsTree } from "../components/ObjectsTree";
import { RiskCard } from "./RiskCard";
import type { ObjectsTreeResponse, RiskCaseOut } from "../api/types";

const STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  observing: "Наблюдение",
  dispatched: "Направлено",
  rejected: "Отклонён",
  resolved: "Решён",
};

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

  return (
    <div className="page risks-page">
      <div className="page-toolbar">
        <div className="view-toggle">
          <button className={view === "list" ? "active" : ""} onClick={() => setView("list")}>
            Список
          </button>
          <button className={view === "scheme" ? "active" : ""} onClick={() => setView("scheme")}>
            Схема объектов
          </button>
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">Оба направления</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <button onClick={risks.reload}>Обновить</button>
      </div>

      <div className="risks-layout">
        <div className="risks-main">
          {view === "list" ? (
            <DataState
              loading={risks.loading}
              error={risks.error}
              empty={!risks.data?.length}
              emptyText="Активных рисков нет"
            >
              <table className="risk-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Канал</th>
                    <th>Категория</th>
                    <th>Статус</th>
                    <th>Приоритет</th>
                    <th>Открыт</th>
                  </tr>
                </thead>
                <tbody>
                  {risks.data?.map((r) => (
                    <tr
                      key={r.id}
                      className={r.id === selected?.id ? "selected" : ""}
                      onClick={() => setSelected(r)}
                    >
                      <td>{r.id}</td>
                      <td>{r.channel_id}</td>
                      <td>{categoryLabel(r.category)}</td>
                      <td>{STATUS_LABELS[r.status] ?? r.status}</td>
                      <td>{r.priority ?? "—"}</td>
                      <td>{new Date(r.opened_at).toLocaleString("ru-RU")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                  <p className="map-footnote">
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
          <div className="risks-side">
            <RiskCard riskCase={selected} onDecided={() => risks.reload()} />
          </div>
        )}
      </div>
    </div>
  );
}
