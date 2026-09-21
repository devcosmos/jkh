import { AnomalyBadge } from "./AnomalyBadge";

interface Feature {
  feature: string;
  label: string;
  value: string | number;
  contribution: number;
}

export interface Anomaly {
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

/** Достаёт сигнал «независимой модели» из сырого explanation — для мест, которым нужен
 * только бейдж аномалии отдельно от остального SHAP-объяснения (см. RiskCard.tsx). */
export function getAnomaly(explanation: Record<string, unknown> | null): Anomaly | undefined {
  return (explanation as Explanation | null)?.anomaly;
}

// Дублирует backend/app/workers/replay_worker.py:FEATURE_LABELS — переопределяем на
// клиенте, а не полагаемся на текст, сохранённый в explanation на момент прогноза:
// иначе старые прогнозы в журнале навсегда показывали бы прежнюю формулировку лейбла.
const FEATURE_LABELS: Record<string, string> = {
  n_alarms_1h: "Тревог за 1 час",
  n_alarms_24h: "Тревог за 24 часа",
  n_alarms_7d: "Тревог за 7 суток",
  n_transitions_1h: "Переходов состояния за 1 час",
  n_transitions_24h: "Переходов состояния за 24 часа",
  n_transitions_7d: "Переходов состояния за 7 суток",
  n_events_1h: "Событий за 1 час",
  n_events_24h: "Событий за 24 часа",
  n_events_7d: "Событий за 7 суток",
  seconds_since_last_event: "Время с последнего события",
  n_neighbors_in_fault: "Соседей в отказе",
  frac_neighbors_in_fault: "Доля соседей в отказе",
  current_state: "Текущее состояние",
  тип_датчика: "Тип датчика",
};

function featureLabel(f: Feature): string {
  return FEATURE_LABELS[f.feature] ?? f.label;
}

/** «2471» секунд ничего не говорит диспетчеру на глаз — переводим в наибольшую подходящую
 * единицу (секунды/минуты/часы/дни/недели/месяцы), одно число, без дробей. */
function formatDuration(seconds: number): string {
  const units: [string, number, (n: number) => string][] = [
    ["секунда", 1, pluralSeconds],
    ["минута", 60, pluralMinutes],
    ["час", 3600, pluralHours],
    ["день", 86400, pluralDays],
    ["неделя", 604800, pluralWeeks],
    ["месяц", 2629800, pluralMonths], // 30.44 дня — средний месяц
  ];
  let chosen = units[0];
  for (const u of units) {
    if (seconds >= u[1]) chosen = u;
    else break;
  }
  const [, unitSeconds, format] = chosen;
  const n = Math.max(1, Math.round(seconds / unitSeconds));
  return format(n);
}

function pluralRu(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}
const pluralSeconds = (n: number) => `${n} ${pluralRu(n, "секунда", "секунды", "секунд")}`;
const pluralMinutes = (n: number) => `${n} ${pluralRu(n, "минута", "минуты", "минут")}`;
const pluralHours = (n: number) => `${n} ${pluralRu(n, "час", "часа", "часов")}`;
const pluralDays = (n: number) => `${n} ${pluralRu(n, "день", "дня", "дней")}`;
const pluralWeeks = (n: number) => `${n} ${pluralRu(n, "неделя", "недели", "недель")}`;
const pluralMonths = (n: number) => `${n} ${pluralRu(n, "месяц", "месяца", "месяцев")}`;

function featureValue(f: Feature): string {
  if (f.feature === "seconds_since_last_event" && typeof f.value === "number") {
    return formatDuration(f.value);
  }
  return String(f.value);
}

/** SHAP-вклад признаков в конкретный прогноз (не глобальная важность модели) — считается
 * той же моделью в момент прогноза (backend/app/workers/replay_worker.py:explain_prediction).
 * Положительный вклад толкает вероятность к отказу, отрицательный — от него.
 *
 * `anomaly` — независимый от CatBoost сигнал (IsolationForest без учителя на тех же
 * поведенческих признаках, scripts/train_anomaly_model.py): может отметить необычное
 * поведение, не похожее ни на один известный сценарий отказа в разметке. */
export function ShapExplanation({
  explanation,
  showAnomaly = true,
}: {
  explanation: Record<string, unknown> | null;
  /** RiskCard.tsx выносит бейдж аномалии в заголовок карточки «Аналитика» вместо
   * "Почему сработал прогноз" — здесь его тогда показывать второй раз не нужно. */
  showAnomaly?: boolean;
}) {
  const e = explanation as Explanation | null;
  if (!e?.top_features?.length) {
    return <p className="text-sm text-slate-400">Объяснение для этого прогноза недоступно</p>;
  }

  const maxAbs = Math.max(...e.top_features.map((f) => Math.abs(f.contribution)), 0.0001);

  return (
    <div className="space-y-2">
      {showAnomaly && e.anomaly && (
        <div className="mb-1">
          <AnomalyBadge isOutlier={e.anomaly.is_outlier} />
        </div>
      )}
      <ul className="flex flex-col gap-y-1.5">
        {e.top_features.map((f) => {
          const positive = f.contribution >= 0;
          // Ширина — доля от максимума среди топ-5; сама показывает силу вклада, цвет
          // (тёплый/холодный) — только направление, без градиента по величине.
          const widthPct = Math.max((Math.abs(f.contribution) / maxAbs) * 100, 10);
          return (
            <li key={f.feature} className="relative w-full overflow-hidden rounded-lg">
              <span className="relative z-1 flex w-full items-center justify-between gap-x-2 px-2.5 py-1.5 text-sm">
                <span className="text-slate-700">{featureLabel(f)}</span>
                <span className="shrink-0 font-medium text-slate-500">{featureValue(f)}</span>
              </span>
              <div
                className={`absolute inset-y-0 left-0 h-full ${positive ? "bg-red-100" : "bg-sky-100"}`}
                style={{ width: `${widthPct}%` }}
              />
            </li>
          );
        })}
      </ul>
      <p className="flex items-center gap-x-3 pt-0.5 text-sm text-slate-400">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-300" />
          повышает риск отказа
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 shrink-0 rounded-full bg-sky-300" />
          понижает риск отказа
        </span>
      </p>
    </div>
  );
}
