import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { DECISION_ACTION_LABELS } from "../api/decisionAction";
import { RISK_STATUS_LABELS, RISK_STATUS_TONE } from "../api/riskStatus";
import { useApi } from "../api/useApi";
import { Badge, riskPriorityTone } from "../components/Badge";
import { DataState } from "../components/DataState";
import { DegradationTrendBadge } from "../components/DegradationTrendBadge";
import { Select } from "../components/Select";
import { ShapExplanation } from "../components/ShapExplanation";
import type {
  ChannelOut,
  DecisionAction,
  DegradationTrendOut,
  EpisodeOut,
  MaintenanceRequestOut,
  PredictionOut,
  RiskCaseOut,
} from "../api/types";

const ACTIONS: { value: DecisionAction; label: string; primary?: boolean }[] = [
  { value: "dispatch", label: DECISION_ACTION_LABELS.dispatch, primary: true },
  { value: "observe", label: DECISION_ACTION_LABELS.observe },
  { value: "clarify", label: DECISION_ACTION_LABELS.clarify },
  { value: "reject", label: DECISION_ACTION_LABELS.reject },
];

// Справочник причин — раздел 12 ТЗ прямо требует «фиксирует решение… с выбором причины
// из справочника», не только свободный текст. Выбор подставляет формулировку в поле
// комментария, которое остаётся редактируемым — не жёсткий enum на backend, чтобы не
// плодить миграцию под каждую новую причину.
const REASON_CATALOG = [
  "Ложное срабатывание датчика",
  "Известная неисправность, уже устраняется",
  "Плановое обслуживание рядом с объектом",
  "Подтверждено визуальным осмотром/камерой",
  "Недостаточно данных для решения",
  "Похоже на реальный риск — требует проверки",
];

export function RiskCard({ riskCase, onDecided }: { riskCase: RiskCaseOut; onDecided: () => void }) {
  const channel = useApi<ChannelOut>(() => api.get(`/channels/${riskCase.channel_id}`), [riskCase.channel_id]);
  const episodes = useApi<EpisodeOut[]>(
    () => api.get(`/channels/${riskCase.channel_id}/episodes`),
    [riskCase.channel_id]
  );
  const latestPrediction = useApi<PredictionOut[]>(
    // По risk_case_id, не по channel_id+category — иначе для уже закрытого риск-кейса
    // здесь показывался бы ПОСЛЕДНИЙ прогноз воркера по каналу вообще (текущий тик), а не
    // тот, что реально был при открытии именно этого кейса.
    () => api.get(`/predictions?risk_case_id=${riskCase.id}&limit=1`),
    [riskCase.id]
  );
  const latestPredictionId = latestPrediction.data?.[0]?.id;
  // Лениво по конкретному прогнозу, а не для всех сразу — см. TODO.md: считается один раз
  // при первом открытии карточки, результат кешируется на backend (Prediction.llm_summary).
  const llmSummary = useApi<{ summary: string | null } | null>(
    () => (latestPredictionId ? api.get(`/predictions/${latestPredictionId}/summary`) : Promise.resolve(null)),
    [latestPredictionId]
  );
  const requestsForCase = useApi<MaintenanceRequestOut[]>(
    () => api.get(`/maintenance-requests?risk_case_id=${riskCase.id}&limit=1`),
    [riskCase.id]
  );
  const trend = useApi<DegradationTrendOut>(
    () => api.get(`/channels/${riskCase.channel_id}/degradation-trend`),
    [riskCase.channel_id]
  );
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastDecision, setLastDecision] = useState<string | null>(null);

  const currentEpisode = episodes.data?.find((e) => !e.end_time);

  async function submitDecision(action: DecisionAction) {
    setSubmitting(true);
    setActionError(null);
    try {
      await api.post(`/risk-cases/${riskCase.id}/decisions`, { action, reason: reason || null });
      setReason("");
      setLastDecision(ACTIONS.find((a) => a.value === action)?.label ?? action);
      requestsForCase.reload();
      onDecided();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-y-2">
        <h3 className="font-display text-base font-semibold text-slate-900">Риск-кейс #{riskCase.id}</h3>
        <div className="flex items-center gap-2">
          <Badge tone={RISK_STATUS_TONE[riskCase.status] ?? "neutral"} dot>
            {RISK_STATUS_LABELS[riskCase.status] ?? riskCase.status}
          </Badge>
          {riskCase.priority && (
            <Badge tone={riskPriorityTone(riskCase.priority)}>
              {riskCase.priority === "high" ? "Высокий приоритет" : "Средний приоритет"}
            </Badge>
          )}
        </div>
      </div>

      {!lastDecision && requestsForCase.data?.[0] && (
        <Link
          to={`/requests?risk_case_id=${riskCase.id}`}
          className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm font-medium text-slate-600 hover:border-sky-300 hover:text-sky-700"
        >
          <span>По этому риск-кейсу уже есть заявка на обслуживание</span>
          <span className="shrink-0 font-semibold">Смотреть →</span>
        </Link>
      )}

      <div>
        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Канал</h4>
        <DataState loading={channel.loading} error={channel.error} empty={!channel.data} emptyText="Канал не найден">
          {channel.data && (
            <div className="rounded-xl bg-slate-50 p-3.5 text-sm">
              <div className="font-semibold text-slate-900">
                {channel.data.display_name ?? `Канал ${channel.data.external_channel_id}`}
              </div>
              <div className="mt-1 text-slate-500">Тип: {channel.data.sensor_type}</div>
              {channel.data.device_label && (
                <div className="text-slate-500">Устройство: {channel.data.device_label}</div>
              )}
              {channel.data.location_tag && (
                <div className="text-slate-500">Расположение: {channel.data.location_tag}</div>
              )}
            </div>
          )}
        </DataState>
      </div>

      {/* Не показывать сломанной, если не загрузилось/нет данных (404 на канале без
          эпизодов) — это дополнительный сигнал, не критичный для карточки. */}
      {trend.data && (
        <div>
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Тренд по каналу</h4>
          <DegradationTrendBadge trend={trend.data} />
        </div>
      )}

      {latestPrediction.data?.[0] && (
        <div>
          <h4 className="mb-2 flex items-baseline gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Почему сработал прогноз
            <span className="text-sm font-semibold normal-case text-slate-900">
              {(latestPrediction.data[0].probability * 100).toFixed(0)}% вероятность отказа
            </span>
          </h4>
          <div className="rounded-xl bg-slate-50 p-3.5">
            {llmSummary.loading ? (
              <p className="mb-3 text-sm text-slate-400 italic">Формируется краткое резюме…</p>
            ) : llmSummary.data?.summary ? (
              <p className="mb-3 border-b border-slate-200 pb-3 text-sm text-slate-700 italic">
                {llmSummary.data.summary}
              </p>
            ) : null}
            <ShapExplanation explanation={latestPrediction.data[0].explanation} />
          </div>
        </div>
      )}

      {/* Текущая неисправность показывается отдельно от прогноза — раздел 9.1 плана. */}
      {currentEpisode && (
        <div className="flex items-start gap-2.5 rounded-xl border border-orange-200 bg-orange-50 px-3.5 py-3 text-sm text-orange-800">
          <span className="mt-0.5 shrink-0">⚠</span>
          <span>
            Устройство сейчас в неисправном состоянии с{" "}
            {new Date(currentEpisode.start_time).toLocaleString("ru-RU")}
            {currentEpisode.left_censored && " (возможно, продолжение более раннего отказа)"}
          </span>
        </div>
      )}

      <div>
        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Решение диспетчера</h4>
        <Select
          value=""
          onChange={(e) => {
            if (e.target.value) setReason(e.target.value);
          }}
          className="mb-2 w-full"
        >
          <option value="">Причина из справочника…</option>
          {REASON_CATALOG.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
        <textarea
          className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
          rows={2}
          placeholder="Причина (необязательно)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {ACTIONS.map((a) => (
            <button
              key={a.value}
              disabled={submitting}
              onClick={() => submitDecision(a.value)}
              className={`rounded-xl px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                a.primary
                  ? "bg-sky-500 text-white hover:bg-sky-600"
                  : "border border-slate-200 text-slate-600 hover:border-slate-300 hover:text-slate-900"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
        {actionError && (
          <div className="mt-3 rounded-xl bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-600">
            {actionError}
          </div>
        )}
        {lastDecision && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50 px-3.5 py-2.5 text-sm font-medium text-emerald-700">
            <span>
              <span className="mr-1.5">✓</span>
              Решение сохранено: «{lastDecision}». Новый статус — «
              {RISK_STATUS_LABELS[riskCase.status] ?? riskCase.status}».
            </span>
            {requestsForCase.data?.[0] && (
              <Link
                to={`/requests?risk_case_id=${riskCase.id}`}
                className="shrink-0 rounded-lg bg-white px-2.5 py-1.5 text-sm font-semibold text-emerald-700 shadow-sm hover:bg-emerald-100"
              >
                Смотреть заявку →
              </Link>
            )}
          </div>
        )}
      </div>

      {/* В конце и со своим скроллом — история эпизодов может быть очень длинной и не должна
          заставлять листать всю карточку до решения диспетчера. */}
      <div>
        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">История эпизодов</h4>
        <DataState
          loading={episodes.loading}
          error={episodes.error}
          empty={!episodes.data?.length}
          emptyText="Эпизодов не зафиксировано"
        >
          <ul className="max-h-56 space-y-2 overflow-y-auto pr-1 text-sm">
            {episodes.data?.map((e) => (
              <li key={e.id} className="flex items-start gap-2 border-l-2 border-slate-200 pl-3">
                <div>
                  <div className="text-slate-700">
                    {new Date(e.start_time).toLocaleString("ru-RU")} —{" "}
                    {e.end_time ? new Date(e.end_time).toLocaleString("ru-RU") : "продолжается"}
                  </div>
                  {e.is_flapping_incident && (
                    <div className="text-sm text-slate-400">помечен как флаппинг/инцидент</div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </DataState>
      </div>
    </div>
  );
}
