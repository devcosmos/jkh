import { Badge } from "./Badge";

interface Feature {
  feature: string;
  label: string;
  value: string | number;
  contribution: number;
}

interface Anomaly {
  method?: string;
  score: number;
  is_outlier: boolean;
}

interface Explanation {
  method?: string;
  base_value?: number;
  top_features?: Feature[];
  anomaly?: Anomaly;
}

/** SHAP-вклад признаков в конкретный прогноз (не глобальная важность модели) — считается
 * той же моделью в момент прогноза (backend/app/workers/replay_worker.py:explain_prediction).
 * Положительный вклад толкает вероятность к отказу, отрицательный — от него.
 *
 * `anomaly` — независимый от CatBoost сигнал (IsolationForest без учителя на тех же
 * поведенческих признаках, scripts/train_anomaly_model.py): может отметить необычное
 * поведение, не похожее ни на один известный сценарий отказа в разметке. */
export function ShapExplanation({ explanation }: { explanation: Record<string, unknown> | null }) {
  const e = explanation as Explanation | null;
  if (!e?.top_features?.length) {
    return <p className="text-sm text-slate-400">Объяснение для этого прогноза недоступно</p>;
  }

  const maxAbs = Math.max(...e.top_features.map((f) => Math.abs(f.contribution)), 0.0001);

  return (
    <div className="space-y-3">
      {e.anomaly && (
        <div className="mb-1">
          {e.anomaly.is_outlier ? (
            <Badge tone="serious">Аномальное поведение (независимая модель)</Badge>
          ) : (
            <Badge tone="neutral">Поведение в норме (независимая модель)</Badge>
          )}
        </div>
      )}
      {e.top_features.map((f) => {
        const positive = f.contribution >= 0;
        const halfWidth = Math.max((Math.abs(f.contribution) / maxAbs) * 50, 3);
        return (
          <div key={f.feature}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="text-slate-700">{f.label}</span>
              <span className="shrink-0 font-medium text-slate-500">{f.value}</span>
            </div>
            <div className="relative h-2 overflow-hidden rounded-full bg-slate-100">
              {/* Нулевая точка вклада — ориентир для «толкает к отказу / от отказа» */}
              <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" />
              <div
                className={`absolute inset-y-0 rounded-full ${positive ? "bg-orange-400" : "bg-sky-400"}`}
                style={
                  positive
                    ? { left: "50%", width: `${halfWidth}%` }
                    : { right: "50%", width: `${halfWidth}%` }
                }
              />
            </div>
          </div>
        );
      })}
      <p className="flex items-center gap-1 pt-1 text-xs text-slate-400">
        <span className="inline-block h-2 w-2 rounded-full bg-orange-400" />
        повышает риск отказа
        <span className="ml-3 inline-block h-2 w-2 rounded-full bg-sky-400" />
        снижает риск отказа
      </p>
    </div>
  );
}
