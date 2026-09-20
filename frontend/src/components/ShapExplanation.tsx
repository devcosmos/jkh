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
    <div className="space-y-2">
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
        const width = Math.max((Math.abs(f.contribution) / maxAbs) * 100, 4);
        return (
          <div key={f.feature} className="flex items-center gap-3 text-sm">
            <div className="w-40 shrink-0 truncate text-slate-600" title={f.label}>
              {f.label}
            </div>
            <div className="flex h-2.5 flex-1 items-center">
              <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`absolute top-0 h-2.5 rounded-full ${positive ? "left-1/2 bg-orange-400" : "right-1/2 bg-sky-400"}`}
                  style={{ width: `${width / 2}%` }}
                />
              </div>
            </div>
            <div className="w-20 shrink-0 text-right text-xs text-slate-500">{f.value}</div>
          </div>
        );
      })}
      <p className="pt-1 text-xs text-slate-400">
        <span className="mr-1 inline-block h-2 w-2 rounded-full bg-orange-400" />
        повышает риск отказа
        <span className="mr-1 ml-3 inline-block h-2 w-2 rounded-full bg-sky-400" />
        снижает риск отказа
      </p>
    </div>
  );
}
