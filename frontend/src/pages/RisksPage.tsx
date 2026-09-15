import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DataState } from "../components/DataState";
import { ObjectsMap } from "../components/ObjectsMap";
import { RiskCard } from "./RiskCard";
import type { ObjectsGeoJson, RiskCaseOut } from "../api/types";

const STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  observing: "Наблюдение",
  dispatched: "Направлено",
  rejected: "Отклонён",
  resolved: "Решён",
};

export function RisksPage() {
  const [view, setView] = useState<"list" | "map">("list");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selected, setSelected] = useState<RiskCaseOut | null>(null);

  const risks = useApi<RiskCaseOut[]>(
    () => api.get(`/risk-cases${statusFilter ? `?status=${statusFilter}` : ""}`),
    [statusFilter]
  );
  const geo = useApi<ObjectsGeoJson>(() => api.get("/objects/geojson"), []);

  return (
    <div className="page risks-page">
      <div className="page-toolbar">
        <div className="view-toggle">
          <button className={view === "list" ? "active" : ""} onClick={() => setView("list")}>
            Список
          </button>
          <button className={view === "map" ? "active" : ""} onClick={() => setView("map")}>
            Карта
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
                      <td>{r.category}</td>
                      <td>{STATUS_LABELS[r.status] ?? r.status}</td>
                      <td>{r.priority ?? "—"}</td>
                      <td>{new Date(r.opened_at).toLocaleString("ru-RU")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DataState>
          ) : (
            <DataState loading={geo.loading} error={geo.error} empty={false} emptyText="">
              {geo.data && (
                <>
                  <ObjectsMap data={geo.data} />
                  <p className="map-footnote">
                    Объектов с проверенной геометрией: {geo.data.n_with_geometry} из{" "}
                    {geo.data.n_total_objects}. Остальные показаны только в списке — раздел 3.2
                    плана: без выдуманных координат.
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
