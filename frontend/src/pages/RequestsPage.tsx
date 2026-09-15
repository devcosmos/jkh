import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DataState } from "../components/DataState";
import type { MaintenanceRequestOut, MaintenanceRequestStatus } from "../api/types";

const STATUS_LABELS: Record<MaintenanceRequestStatus, string> = {
  draft: "Черновик",
  approved: "Утверждена",
  in_progress: "В работе",
  completed: "Выполнена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

// Разрешённые переходы — зеркало ALLOWED_TRANSITIONS на backend (раздел 10 плана).
const NEXT_STATUSES: Record<MaintenanceRequestStatus, MaintenanceRequestStatus[]> = {
  draft: ["approved", "rejected"],
  approved: ["in_progress", "cancelled"],
  in_progress: ["completed", "cancelled"],
  completed: [],
  rejected: [],
  cancelled: [],
};

export function RequestsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const requests = useApi<MaintenanceRequestOut[]>(
    () => api.get(`/maintenance-requests${statusFilter ? `?status=${statusFilter}` : ""}`),
    [statusFilter]
  );

  async function transition(id: number, to: MaintenanceRequestStatus) {
    setBusyId(id);
    setActionError(null);
    try {
      if (to === "approved") {
        await api.post(`/maintenance-requests/${id}/approve`);
      } else {
        await api.post(`/maintenance-requests/${id}/transitions`, { to_status: to });
      }
      requests.reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page requests-page">
      <div className="page-toolbar">
        <h2>Заявки на обслуживание</h2>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <button onClick={requests.reload}>Обновить</button>
      </div>
      {actionError && <div className="state state-error">{actionError}</div>}
      <DataState
        loading={requests.loading}
        error={requests.error}
        empty={!requests.data?.length}
        emptyText="Заявок нет — автосоздание черновиков по правилу ещё не подключено (см. Статус.md)"
      >
        <table className="requests-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Риск-кейс</th>
              <th>Вид работы</th>
              <th>Приоритет</th>
              <th>Статус</th>
              <th>Срок</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {requests.data?.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.risk_case_id}</td>
                <td>{r.work_type}</td>
                <td>{r.priority ?? "—"}</td>
                <td>{STATUS_LABELS[r.status]}</td>
                <td>{r.recommended_by ? new Date(r.recommended_by).toLocaleDateString("ru-RU") : "не назначен"}</td>
                <td>
                  {NEXT_STATUSES[r.status].map((next) => (
                    <button key={next} disabled={busyId === r.id} onClick={() => transition(r.id, next)}>
                      {STATUS_LABELS[next]}
                    </button>
                  ))}
                  {NEXT_STATUSES[r.status].length === 0 && "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </div>
  );
}
