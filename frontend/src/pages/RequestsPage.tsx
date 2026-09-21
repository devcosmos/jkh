import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { usePagedApi } from "../api/usePagedApi";
import { useApi } from "../api/useApi";
import { categoryLabel, categoryTone } from "../api/categories";
import { DECISION_ACTION_LABELS } from "../api/decisionAction";
import { REQUEST_STATUS_LABELS as STATUS_LABELS, REQUEST_STATUS_TONE as STATUS_TONE } from "../api/requestStatus";
import { AnomalyBadge } from "../components/AnomalyBadge";
import { Badge, riskPriorityTone } from "../components/Badge";
import { SECONDARY_CONTROL } from "../components/controlStyles";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import { ChevronIcon } from "../components/icons";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import { exportCsv } from "../lib/exportCsv";
import type { AuditLogEntry, MaintenanceRequestOut, MaintenanceRequestStatus } from "../api/types";

// Разрешённые переходы — зеркало ALLOWED_TRANSITIONS на backend (раздел 10 плана).
const NEXT_STATUSES: Record<MaintenanceRequestStatus, MaintenanceRequestStatus[]> = {
  draft: ["approved", "rejected"],
  approved: ["in_progress", "cancelled"],
  in_progress: ["completed", "cancelled"],
  completed: [],
  rejected: [],
  cancelled: [],
};

// Линейный «счастливый путь» — для наглядного степпера «что было / что будет». reject/cancel
// прерывают его на неизвестном для нас шаге (без полного audit-log это было бы выдумкой),
// поэтому для них степпер не рисуется — только терминальный статус-бейдж.
const HAPPY_PATH: MaintenanceRequestStatus[] = ["draft", "approved", "in_progress", "completed"];

export function RequestsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const riskCaseFilter = searchParams.get("risk_case_id");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<MaintenanceRequestOut | null>(null);

  const requests = usePagedApi<MaintenanceRequestOut>(
    (limit, offset) => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (riskCaseFilter) params.set("risk_case_id", riskCaseFilter);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      return `/maintenance-requests?${params.toString()}`;
    },
    [statusFilter, riskCaseFilter],
    50
  );

  // Та же логика, что на «Рисках»/в «Журнале»: всегда что-то выбрано, если в выборке
  // есть хоть одна строка; после смены/перезагрузки — обновляем данными, но не теряем выбор,
  // если запись осталась в выборке (например, после смены статуса заявки).
  useEffect(() => {
    if (!requests.data) return;
    const stillPresent = selected && requests.data.find((r) => r.id === selected.id);
    if (stillPresent) {
      if (stillPresent !== selected) setSelected(stillPresent);
      return;
    }
    setSelected(requests.data[0] ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requests.data]);

  function clearRiskCaseFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("risk_case_id");
    setSearchParams(next);
  }

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">Заявки на обслуживание</h1>
          <p className="mt-1 text-sm text-slate-500">
            Заявки, созданные решением диспетчера на странице «Риски» — нажмите на строку, чтобы увидеть детали
          </p>
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
            disabled={!requests.data?.length}
            onClick={() =>
              exportCsv(`requests_${new Date().toISOString().slice(0, 10)}.csv`, requests.data ?? [], [
                { header: "ID", value: (r) => r.id },
                { header: "Риск-кейс", value: (r) => r.risk_case_id },
                { header: "Объект", value: (r) => r.object_name ?? "" },
                { header: "Канал", value: (r) => r.channel_label ?? "" },
                { header: "Направление", value: (r) => (r.category ? categoryLabel(r.category) : "") },
                { header: "Вид работы", value: (r) => r.work_type },
                { header: "Приоритет", value: (r) => r.priority ?? "" },
                { header: "Статус", value: (r) => STATUS_LABELS[r.status] },
                { header: "Создана", value: (r) => new Date(r.created_at).toLocaleString("ru-RU") },
              ])
            }
            className={`rounded-xl px-3.5 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${SECONDARY_CONTROL}`}
          >
            Экспорт CSV
          </button>
          <button onClick={requests.reload} className={`rounded-xl px-3.5 py-2 text-sm font-medium ${SECONDARY_CONTROL}`}>
            Обновить
          </button>
        </div>
      </div>

      {riskCaseFilter && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-sky-50 px-4 py-2.5 text-sm text-sky-800">
          <span>
            Показаны заявки только по риск-кейсу{" "}
            <Link to={`/risks?risk_case_id=${riskCaseFilter}`} className="font-semibold underline">
              #{riskCaseFilter}
            </Link>
          </span>
          <button onClick={clearRiskCaseFilter} className="font-medium text-sky-700 hover:text-sky-900">
            Показать все заявки ×
          </button>
        </div>
      )}

      <div className="flex flex-col items-start gap-6 lg:flex-row">
        <div className="min-w-0 w-full flex-1">
          <DataState
            loading={requests.loading}
            error={requests.error}
            empty={!requests.data?.length}
            emptyText="Заявок нет с учётом фильтра"
          >
            <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-3 whitespace-nowrap">ID</th>
                    <th className="px-4 py-3 whitespace-nowrap">Объект / канал</th>
                    <th className="px-4 py-3 whitespace-nowrap">Вид работы</th>
                    <th className="px-4 py-3 whitespace-nowrap">Приоритет</th>
                    <th className="px-4 py-3 whitespace-nowrap">Статус</th>
                    <th className="px-4 py-3 whitespace-nowrap">Создана</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {requests.data?.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setSelected(r)}
                      className={`cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 ${
                        r.id === selected?.id ? "bg-sky-100 hover:bg-sky-100" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-medium whitespace-nowrap text-slate-400">#{r.id}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium whitespace-nowrap text-slate-900">
                          {r.object_name ?? "объект не определён"}
                        </div>
                        <div className="text-sm whitespace-nowrap text-slate-500">
                          {r.channel_label ?? `канал #${r.risk_case_id}`}
                          {r.category && (
                            <span className="ml-1.5">
                              <Badge tone={categoryTone(r.category)}>{categoryLabel(r.category)}</Badge>
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-medium whitespace-nowrap text-slate-900">{r.work_type}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {r.priority ? (
                          <Badge tone={riskPriorityTone(r.priority)} icon="priority">
                            {r.priority === "high" ? "Высокий" : "Средний"}
                          </Badge>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Badge tone={STATUS_TONE[r.status]} dot>
                          {STATUS_LABELS[r.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                        {new Date(r.created_at).toLocaleDateString("ru-RU")}
                      </td>
                      <td className="px-4 py-3 text-slate-400">
                        <ChevronIcon className="h-5 w-5" strokeWidth={2.6} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={requests.page}
                pageSize={requests.pageSize}
                total={requests.total}
                loadedCount={requests.data?.length ?? 0}
                onPageChange={requests.setPage}
              />
            </div>
          </DataState>
        </div>

        <div className="w-full shrink-0 lg:w-120">
          {selected ? (
            <RequestDetail key={selected.id} request={selected} onChanged={() => requests.reload()} />
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <p className="text-sm text-slate-500">Выберите заявку в таблице слева, чтобы увидеть обоснование и ход выполнения</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RequestDetail({ request, onChanged }: { request: MaintenanceRequestOut; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function transition(to: MaintenanceRequestStatus) {
    setBusy(true);
    setActionError(null);
    try {
      if (to === "approved") {
        await api.post(`/maintenance-requests/${request.id}/approve`);
      } else {
        await api.post(`/maintenance-requests/${request.id}/transitions`, { to_status: to });
      }
      onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-y-2 px-1">
        <h3 className="font-display text-base font-semibold text-slate-900">Заявка #{request.id}</h3>
        <div className="flex items-center gap-2">
          <Badge tone={STATUS_TONE[request.status]} dot>
            {STATUS_LABELS[request.status]}
          </Badge>
          {request.priority && (
            <Badge tone={riskPriorityTone(request.priority)} icon="priority">
              {request.priority === "high" ? "Высокий приоритет" : "Средний приоритет"}
            </Badge>
          )}
        </div>
      </div>

      <Link
        to={`/risks?risk_case_id=${request.risk_case_id}`}
        className={`flex items-center justify-between rounded-xl px-3.5 py-2.5 text-sm font-medium ${SECONDARY_CONTROL}`}
      >
        <span>
          {request.object_name ?? "объект не определён"} — {request.channel_label ?? `канал #${request.risk_case_id}`}
        </span>
        <span className="flex shrink-0 items-center gap-1 font-semibold">
          Риск-кейс
          <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
        </span>
      </Link>

      <DetailSection
        title="Обоснование"
        right={request.anomaly_is_outlier !== null && <AnomalyBadge isOutlier={request.anomaly_is_outlier} />}
      >
        {request.ai_summary && (
          <p className="border-b border-slate-100 pb-3 text-sm text-slate-700 italic">{request.ai_summary}</p>
        )}
        {/* Раньше был единый абзац "Канал: ...\nОбъект: ...\nКатегория риска: ...\nСрок: ...",
            сгенерированный на бэкенде (ensure_request_for_dispatch) — те же значения уже
            приходят отдельными полями в MaintenanceRequestOut, строим из них строки, а не
            парсим текст. */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-x-2">
            <span className="text-sm text-slate-500">Канал</span>
            <span className="text-sm font-medium text-slate-700">
              {request.channel_label ?? `канал #${request.risk_case_id}`}
            </span>
          </div>
          <div className="flex items-center justify-between gap-x-2">
            <span className="text-sm text-slate-500">Объект</span>
            <span className="text-sm font-medium text-slate-700">{request.object_name ?? "не определён"}</span>
          </div>
          <div className="flex items-center justify-between gap-x-2">
            <span className="text-sm text-slate-500">Направление</span>
            {request.category ? (
              <Badge tone={categoryTone(request.category)}>{categoryLabel(request.category)}</Badge>
            ) : (
              <span className="text-sm text-slate-400">—</span>
            )}
          </div>
          <div className="flex items-center justify-between gap-x-2">
            <span className="text-sm text-slate-500">Срок</span>
            <span className="text-sm font-medium text-slate-700">не определён</span>
          </div>
        </div>
        {(request.dispatcher_reason || request.dispatcher_action) && (
          <div className="border-t border-slate-100 pt-3">
            <div className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">Решение диспетчера</div>
            <p className="text-sm text-slate-700">
              {request.dispatcher_action && (
                <span className="font-medium">
                  {DECISION_ACTION_LABELS[request.dispatcher_action]}
                  {request.dispatcher_username ? ` — ${request.dispatcher_username}` : ""}
                </span>
              )}
              {request.dispatcher_reason && <span className="block text-slate-600">{request.dispatcher_reason}</span>}
            </p>
          </div>
        )}
      </DetailSection>

      <DetailSection title="Действия">
        <div className="flex flex-wrap gap-2">
          {NEXT_STATUSES[request.status].map((next) => (
            <button
              key={next}
              disabled={busy}
              onClick={() => transition(next)}
              className={`rounded-xl px-3.5 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${SECONDARY_CONTROL}`}
            >
              {STATUS_LABELS[next]}
            </button>
          ))}
          {NEXT_STATUSES[request.status].length === 0 && (
            <p className="text-sm text-slate-400">Статус заявки терминальный — дальнейших переходов нет</p>
          )}
        </div>
        {actionError && (
          <div className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-600">{actionError}</div>
        )}
      </DetailSection>

      <DetailSection title="Ход выполнения">
        <RequestTimeline request={request} />
      </DetailSection>

      <DetailSection title="История">
        <RequestHistory requestId={request.id} />
      </DetailSection>
    </div>
  );
}

// Кто что нажимал, на какой стадии и что писал — TODO пункт 3 («расширить функционал
// заявок» — подробная история).
function RequestHistory({ requestId }: { requestId: number }) {
  const history = useApi<AuditLogEntry[]>(() => api.get(`/maintenance-requests/${requestId}/history`), [requestId]);

  if (history.loading) {
    return <p className="text-sm text-slate-400 italic">Загрузка истории…</p>;
  }
  if (history.error) {
    return <p className="text-sm text-red-600">{history.error}</p>;
  }
  if (!history.data?.length) {
    return <p className="text-sm text-slate-400">Изменений ещё не было</p>;
  }

  return (
    <ul className="max-h-56 space-y-2 overflow-y-auto pr-1 text-sm">
      {history.data.map((entry) => {
        const from = entry.old_state?.status as string | undefined;
        const to = entry.new_state?.status as string | undefined;
        return (
          <li key={entry.id} className="flex items-start gap-2 border-l-2 border-slate-200 pl-3">
            <div>
              <div className="text-slate-700">
                {new Date(entry.created_at).toLocaleString("ru-RU")}
                {entry.username && <span className="ml-1.5 font-medium text-slate-900">{entry.username}</span>}
              </div>
              <div className="text-slate-500">
                {from && to
                  ? `${STATUS_LABELS[from as MaintenanceRequestStatus] ?? from} → ${
                      STATUS_LABELS[to as MaintenanceRequestStatus] ?? to
                    }`
                  : to
                    ? `Статус: ${STATUS_LABELS[to as MaintenanceRequestStatus] ?? to}`
                    : null}
              </div>
              {entry.reason && <div className="text-sm text-slate-400">{entry.reason}</div>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function RequestTimeline({ request }: { request: MaintenanceRequestOut }) {
  const isStopped = request.status === "rejected" || request.status === "cancelled";

  if (isStopped) {
    return (
      <div className="space-y-1.5 text-sm">
        <div className="flex justify-between text-slate-500">
          <span>Создана</span>
          <span className="font-medium text-slate-700">{new Date(request.created_at).toLocaleString("ru-RU")}</span>
        </div>
        <Badge tone={STATUS_TONE[request.status]}>{STATUS_LABELS[request.status]}</Badge>
      </div>
    );
  }

  const currentIndex = HAPPY_PATH.indexOf(request.status);
  return (
    <div>
      <ol className="space-y-2">
        {HAPPY_PATH.map((stage, i) => {
          const reached = i <= currentIndex;
          const isCurrent = i === currentIndex;
          return (
            <li key={stage} className="flex items-center gap-2 text-sm">
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${
                  reached ? "bg-sky-500" : "border border-slate-300 bg-white"
                }`}
              >
                {reached && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
              </span>
              <span className={isCurrent ? "font-semibold text-slate-900" : reached ? "text-slate-700" : "text-slate-400"}>
                {STATUS_LABELS[stage]}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 space-y-1 border-t border-slate-200 pt-2 text-sm text-slate-500">
        <div className="flex justify-between">
          <span>Создана</span>
          <span className="font-medium text-slate-700">{new Date(request.created_at).toLocaleString("ru-RU")}</span>
        </div>
        {request.approved_at && (
          <div className="flex justify-between">
            <span>Утверждена{request.approved_by_username ? ` (${request.approved_by_username})` : ""}</span>
            <span className="font-medium text-slate-700">{new Date(request.approved_at).toLocaleString("ru-RU")}</span>
          </div>
        )}
      </div>
    </div>
  );
}
