import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DataState } from "../components/DataState";
import type { ChannelOut, DecisionAction, EpisodeOut, RiskCaseOut } from "../api/types";

const ACTIONS: { value: DecisionAction; label: string }[] = [
  { value: "observe", label: "Наблюдать" },
  { value: "dispatch", label: "Направить на проверку" },
  { value: "reject", label: "Отклонить предупреждение" },
  { value: "clarify", label: "Уточнить данные" },
];

export function RiskCard({ riskCase, onDecided }: { riskCase: RiskCaseOut; onDecided: () => void }) {
  const channel = useApi<ChannelOut>(() => api.get(`/channels/${riskCase.channel_id}`), [riskCase.channel_id]);
  const episodes = useApi<EpisodeOut[]>(
    () => api.get(`/channels/${riskCase.channel_id}/episodes`),
    [riskCase.channel_id]
  );
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const currentEpisode = episodes.data?.find((e) => !e.end_time);

  async function submitDecision(action: DecisionAction) {
    setSubmitting(true);
    setActionError(null);
    try {
      await api.post(`/risk-cases/${riskCase.id}/decisions`, { action, reason: reason || null });
      setReason("");
      onDecided();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="risk-card">
      <h3>Риск-кейс #{riskCase.id}</h3>
      <DataState loading={channel.loading} error={channel.error} empty={!channel.data} emptyText="Канал не найден">
        {channel.data && (
          <div className="channel-info">
            <div>
              <b>{channel.data.display_name ?? `Канал ${channel.data.external_channel_id}`}</b>
            </div>
            <div>Тип: {channel.data.sensor_type}</div>
            {channel.data.location_tag && <div>Расположение: {channel.data.location_tag}</div>}
          </div>
        )}
      </DataState>

      {/* Текущая неисправность показывается отдельно от прогноза — раздел 9.1 плана. */}
      {currentEpisode && (
        <div className="current-fault-banner">
          ⚠ Устройство сейчас в неисправном состоянии с{" "}
          {new Date(currentEpisode.start_time).toLocaleString("ru-RU")}
          {currentEpisode.left_censored && " (возможно, продолжение более раннего отказа)"}
        </div>
      )}

      <h4>История эпизодов</h4>
      <DataState
        loading={episodes.loading}
        error={episodes.error}
        empty={!episodes.data?.length}
        emptyText="Эпизодов не зафиксировано"
      >
        <ul className="episode-list">
          {episodes.data?.map((e) => (
            <li key={e.id}>
              {new Date(e.start_time).toLocaleString("ru-RU")} —{" "}
              {e.end_time ? new Date(e.end_time).toLocaleString("ru-RU") : "продолжается"}
              {e.is_flapping_incident && " (помечен как флаппинг/инцидент)"}
            </li>
          ))}
        </ul>
      </DataState>

      <h4>Решение диспетчера</h4>
      <textarea
        placeholder="Причина (необязательно)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="decision-actions">
        {ACTIONS.map((a) => (
          <button key={a.value} disabled={submitting} onClick={() => submitDecision(a.value)}>
            {a.label}
          </button>
        ))}
      </div>
      {actionError && <div className="state state-error">{actionError}</div>}
    </div>
  );
}
