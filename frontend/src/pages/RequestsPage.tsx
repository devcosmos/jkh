import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge, riskPriorityTone } from "../components/Badge";
import { DataState } from "../components/DataState";
import { Select } from "../components/Select";
import type { MaintenanceRequestOut, MaintenanceRequestStatus } from "../api/types";

const STATUS_LABELS: Record<MaintenanceRequestStatus, string> = {
  draft: "Черновик",
  approved: "Утверждена",
  in_progress: "В работе",
  completed: "Выполнена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

const STATUS_TONE: Record<MaintenanceRequestStatus, "neutral" | "warning" | "good"> = {
  draft: "warning",
  approved: "neutral",
  in_progress: "neutral",
  completed: "good",
  rejected: "neutral",
  cancelled: "neutral",
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
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Заявки на обслуживание</h1>
          <p className="mt-1 text-sm text-slate-500">Автоматические черновики и решения диспетчера</p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
          <button
            onClick={requests.reload}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900"
          >
            Обновить
          </button>
        </div>
      </div>

      {actionError && (
        <div className="mb-4 rounded-xl bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-600">
          {actionError}
        </div>
      )}

      <DataState
        loading={requests.loading}
        error={requests.error}
        empty={!requests.data?.length}
        emptyText="Заявок нет с учётом фильтра"
      >
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Риск-кейс</th>
                <th className="px-4 py-3">Вид работы</th>
                <th className="px-4 py-3">Приоритет</th>
                <th className="px-4 py-3">Статус</th>
                <th className="px-4 py-3">Срок</th>
                <th className="px-4 py-3">Действия</th>
              </tr>
            </thead>
            <tbody>
              {requests.data?.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-400">#{r.id}</td>
                  <td className="px-4 py-3 text-slate-700">{r.risk_case_id}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">{r.work_type}</td>
                  <td className="px-4 py-3">
                    {r.priority ? (
                      <Badge tone={riskPriorityTone(r.priority)}>
                        {r.priority === "high" ? "Высокий" : "Средний"}
                      </Badge>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[r.status]} dot>
                      {STATUS_LABELS[r.status]}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {r.recommended_by ? new Date(r.recommended_by).toLocaleDateString("ru-RU") : "не назначен"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {NEXT_STATUSES[r.status].map((next) => (
                        <button
                          key={next}
                          disabled={busyId === r.id}
                          onClick={() => transition(r.id, next)}
                          className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {STATUS_LABELS[next]}
                        </button>
                      ))}
                      {NEXT_STATUSES[r.status].length === 0 && <span className="text-slate-400">—</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataState>
    </div>
  );
}
