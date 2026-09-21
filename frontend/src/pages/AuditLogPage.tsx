import { useState } from "react";
import { usePagedApi } from "../api/usePagedApi";
import { DataState } from "../components/DataState";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import type { AuditLogEntry } from "../api/types";

const ENTITY_TYPE_LABELS: Record<string, string> = {
  risk_case: "Риск-кейс",
  maintenance_request: "Заявка",
  user_object_access: "Доступ к объекту",
  user: "Пользователь",
};

function formatState(state: Record<string, unknown> | null): string {
  if (!state) return "—";
  return Object.entries(state)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

export function AuditLogPage() {
  const [entityType, setEntityType] = useState("");
  const log = usePagedApi<AuditLogEntry>(
    (limit, offset) => `/audit-log?limit=${limit}&offset=${offset}${entityType ? `&entity_type=${entityType}` : ""}`,
    [entityType],
    50
  );

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Журнал аудита</h1>
          <p className="mt-1 text-sm text-slate-500">Все решения, переходы и изменения доступа — для трассируемости</p>
        </div>
        <Select value={entityType} onChange={(e) => setEntityType(e.target.value)}>
          <option value="">Все типы</option>
          {Object.entries(ENTITY_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>

      <DataState loading={log.loading} error={log.error} empty={!log.data?.length} emptyText="Записей нет">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Время</th>
                <th className="px-4 py-3">Кто</th>
                <th className="px-4 py-3">Тип</th>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Изменение</th>
                <th className="px-4 py-3">Причина</th>
              </tr>
            </thead>
            <tbody>
              {log.data?.map((e) => (
                <tr key={e.id} className="border-b border-slate-100 last:border-0 align-top">
                  <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                    {new Date(e.created_at).toLocaleString("ru-RU")}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{e.username ?? "система"}</td>
                  <td className="px-4 py-3 text-slate-700">{ENTITY_TYPE_LABELS[e.entity_type] ?? e.entity_type}</td>
                  <td className="px-4 py-3 font-medium text-slate-400">#{e.entity_id}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {e.old_state && <div>было: {formatState(e.old_state)}</div>}
                    {e.new_state && <div>стало: {formatState(e.new_state)}</div>}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{e.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            page={log.page}
            pageSize={log.pageSize}
            total={log.total}
            loadedCount={log.data?.length ?? 0}
            onPageChange={log.setPage}
          />
        </div>
      </DataState>
    </div>
  );
}
