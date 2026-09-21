import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { DECISION_ACTION_LABELS } from "../api/decisionAction";
import { RISK_STATUS_LABELS, RISK_STATUS_TONE } from "../api/riskStatus";
import { useApi } from "../api/useApi";
import { AnomalyBadge } from "../components/AnomalyBadge";
import { Badge, riskPriorityTone } from "../components/Badge";
import { PRIMARY_CONTROL, SECONDARY_CONTROL, SECONDARY_FIELD } from "../components/controlStyles";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import { DegradationTrendBadge } from "../components/DegradationTrendBadge";
import { ChevronIcon } from "../components/icons";
import { InfoTooltip } from "../components/InfoTooltip";
import { Select } from "../components/Select";
import { getAnomaly, ShapExplanation } from "../components/ShapExplanation";
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
  const predictionAnomaly = getAnomaly(latestPrediction.data?.[0]?.explanation ?? null);
  // Пока заявка активна (не отклонена/не отменена), дальше по этому риску нечего решать —
  // observe/clarify/reject противоречили бы уже идущей заявке (риск мог бы "откатиться" в
  // наблюдение, пока заявка всё ещё в работе), а dispatch лишь идемпотентно вернёт ту же
  // заявку. Дальнейшие шаги — на странице «Заявки».
  const activeRequest = requestsForCase.data?.find((r) => r.status !== "rejected" && r.status !== "cancelled");

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
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-y-2 px-1">
        <h3 className="font-display text-base font-semibold text-slate-900">Риск-кейс #{riskCase.id}</h3>
        <div className="flex items-center gap-2">
          <Badge tone={RISK_STATUS_TONE[riskCase.status] ?? "neutral"} dot>
            {RISK_STATUS_LABELS[riskCase.status] ?? riskCase.status}
          </Badge>
          {riskCase.priority && (
            <Badge tone={riskPriorityTone(riskCase.priority)} icon="priority">
              {riskCase.priority === "high" ? "Высокий приоритет" : "Средний приоритет"}
            </Badge>
          )}
        </div>
      </div>

      {!lastDecision && activeRequest && (
        <Link
          to={`/requests?risk_case_id=${riskCase.id}`}
          className={`flex items-center justify-between rounded-xl px-3.5 py-2.5 text-sm font-medium ${SECONDARY_CONTROL}`}
        >
          <span>По этому риск-кейсу уже есть заявка на обслуживание</span>
          <span className="flex shrink-0 items-center gap-1 font-semibold">
            Смотреть
            <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
          </span>
        </Link>
      )}

      <DetailSection
        title="Данные"
        right={
          channel.data && (
            <span className="text-sm font-semibold text-slate-900">
              {channel.data.display_name ?? `Канал ${channel.data.external_channel_id}`}
            </span>
          )
        }
      >
        <DataState loading={channel.loading} error={channel.error} empty={!channel.data} emptyText="Канал не найден">
          {channel.data && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-x-2">
                <span className="text-sm text-slate-500">Тип</span>
                <span className="text-sm font-medium text-slate-700">{channel.data.sensor_type}</span>
              </div>
              {channel.data.device_label && (
                <div className="flex items-center justify-between gap-x-2">
                  <span className="text-sm text-slate-500">Устройство</span>
                  <span className="text-sm font-medium text-slate-700">{channel.data.device_label}</span>
                </div>
              )}
              {channel.data.location_tag && (
                <div className="flex items-center justify-between gap-x-2">
                  <span className="text-sm text-slate-500">Расположение</span>
                  <span className="text-sm font-medium text-slate-700">{channel.data.location_tag}</span>
                </div>
              )}
            </div>
          )}
        </DataState>

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
      </DetailSection>

      {latestPrediction.data?.[0] && (
        <DetailSection
          title="Аналитика"
          right={predictionAnomaly && <AnomalyBadge isOutlier={predictionAnomaly.is_outlier} />}
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-x-2">
              <span className="flex items-center gap-1 text-sm text-slate-500">
                Вероятность отказа
                <InfoTooltip text="Оценка модели на ближайшие сутки — не гарантия, а мера уверенности на основе истории похожих случаев по этому направлению." />
              </span>
              <span className="text-sm font-semibold text-slate-900">
                {(latestPrediction.data[0].probability * 100).toFixed(0)}%
              </span>
            </div>
            {/* Не показывать сломанной, если не загрузилось/нет данных (404 на канале без
                эпизодов) — это дополнительный сигнал, не критичный для карточки. */}
            {trend.data && (
              <div className="flex items-center justify-between gap-x-2">
                <span className="flex items-center gap-1 text-sm text-slate-500">
                  Тренд
                  <InfoTooltip text="Динамика частоты неисправностей этого канала за последнее время по сравнению с более длинным периодом — учащаются они, становятся реже или остаются на том же уровне." />
                </span>
                <DegradationTrendBadge trend={trend.data} />
              </div>
            )}
          </div>
          {llmSummary.loading ? (
            <p className="text-sm text-slate-400 italic">Формируется краткое резюме…</p>
          ) : llmSummary.data?.summary ? (
            <p className="border-b border-slate-100 pb-3 text-sm text-slate-700 italic">{llmSummary.data.summary}</p>
          ) : null}
          <ShapExplanation explanation={latestPrediction.data[0].explanation} showAnomaly={false} />
        </DetailSection>
      )}

      <DetailSection
        title="Действия диспетчера"
        right={
          requestsForCase.data?.[0] && (
            <Link
              to={`/requests?risk_case_id=${riskCase.id}`}
              className={`flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm font-semibold ${SECONDARY_CONTROL}`}
            >
              Смотреть заявку
              <ChevronIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
            </Link>
          )
        }
      >
        {lastDecision && (
          <div className="rounded-xl bg-emerald-50 px-3.5 py-2.5 text-sm font-medium text-emerald-700">
            <span className="mr-1.5">✓</span>
            Решение сохранено: «{lastDecision}». Новый статус — «
            {RISK_STATUS_LABELS[riskCase.status] ?? riskCase.status}».
          </div>
        )}
        {activeRequest ? (
          <p className="text-sm text-slate-500">
            По этому риску уже создана и ведётся заявка на обслуживание — дальнейшие решения принимаются на
            странице «Заявки» (утверждение, ход работ), новое решение здесь не требуется.
          </p>
        ) : (
          <>
            <Select
              value=""
              onChange={(e) => {
                if (e.target.value) setReason(e.target.value);
              }}
              className="w-full"
            >
              <option value="">Причина из справочника…</option>
              {REASON_CATALOG.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
            <textarea
              className={`w-full resize-none rounded-xl px-3 py-2.5 text-sm ${SECONDARY_FIELD}`}
              rows={2}
              placeholder="Причина (необязательно)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              {ACTIONS.map((a) => (
                <button
                  key={a.value}
                  disabled={submitting}
                  onClick={() => submitDecision(a.value)}
                  className={`rounded-xl px-3.5 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
                    a.primary ? PRIMARY_CONTROL : SECONDARY_CONTROL
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
            {actionError && (
              <div className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-600">{actionError}</div>
            )}
          </>
        )}
      </DetailSection>

      {/* Своя прокрутка — история эпизодов может быть очень длинной и не должна
          заставлять листать всю карточку до решения диспетчера. */}
      <DetailSection title="История">
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
      </DetailSection>
    </div>
  );
}
