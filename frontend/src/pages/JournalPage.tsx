import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { DataState } from "../components/DataState";
import type { PredictionOut } from "../api/types";

// «Устаревшее» состояние: последний прогноз старше окна прогноза (24ч) — раздел 2 ТЗ.
const STALE_AFTER_HOURS = 24;

export function JournalPage() {
  const predictions = useApi<PredictionOut[]>(() => api.get("/predictions?limit=200"), []);

  return (
    <div className="page journal-page">
      <div className="page-toolbar">
        <h2>Журнал прогнозов</h2>
        <button onClick={predictions.reload}>Обновить</button>
      </div>
      <DataState
        loading={predictions.loading}
        error={predictions.error}
        empty={!predictions.data?.length}
        emptyText="Прогнозов ещё нет — модель либо не запускалась, либо все каналы в норме"
      >
        <table className="journal-table">
          <thead>
            <tr>
              <th>Время расчёта</th>
              <th>Канал</th>
              <th>Категория</th>
              <th>Вероятность</th>
              <th>Окно</th>
              <th>Качество данных</th>
            </tr>
          </thead>
          <tbody>
            {predictions.data?.map((p) => {
              const ageHours = (Date.now() - new Date(p.created_at).getTime()) / 3600_000;
              const stale = ageHours > STALE_AFTER_HOURS;
              return (
                <tr key={p.id} className={stale ? "stale-row" : ""}>
                  <td>{new Date(p.created_at).toLocaleString("ru-RU")}</td>
                  <td>{p.channel_id}</td>
                  <td>{p.category}</td>
                  <td>{(p.probability * 100).toFixed(1)}%</td>
                  <td>
                    {new Date(p.window_start).toLocaleTimeString("ru-RU")}–
                    {new Date(p.window_end).toLocaleTimeString("ru-RU")}
                  </td>
                  <td>
                    {p.data_quality_flag ?? "ok"}
                    {stale && " · устарел"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </DataState>
    </div>
  );
}
