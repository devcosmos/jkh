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

// Интенсивность цвета — по той же доле от максимума среди топ-5, что уже задаёт ширину
// полосы (не отдельная абсолютная шкала, как раньше): чем ближе полоса к 100% ширины,
// тем краснее (или синее для отрицательного вклада) её заливка.
function positiveColor(t: number): string {
  // fed7aa (бледно-оранжевый) -> b91c1c (тёмно-красный)
  return lerpColor([0xfe, 0xd7, 0xaa], [0xb9, 0x1c, 0x1c], t);
}
function negativeColor(t: number): string {
  // bae6fd (бледно-голубой) -> 1d4ed8 (тёмно-синий)
  return lerpColor([0xba, 0xe6, 0xfd], [0x1d, 0x4e, 0xd8], t);
}
function lerpColor(a: [number, number, number], b: [number, number, number], t: number): string {
  const mix = a.map((c, i) => Math.round(c + (b[i] - c) * t));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
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
    <div className="space-y-3">
      {showAnomaly && e.anomaly && (
        <div className="mb-2">
          <AnomalyBadge isOutlier={e.anomaly.is_outlier} />
        </div>
      )}
      {e.top_features.map((f) => {
        const positive = f.contribution >= 0;
        const ratio = Math.abs(f.contribution) / maxAbs; // та же доля, что и ширина полосы
        const halfWidth = Math.max(ratio * 50, 3);
        const color = positive ? positiveColor(ratio) : negativeColor(ratio);
        return (
          <div key={f.feature}>
            <div className="mb-1 flex items-baseline justify-between gap-x-2 text-sm">
              <span className="text-slate-500">{featureLabel(f)}</span>
              <span className="shrink-0 font-medium text-slate-700">{featureValue(f)}</span>
            </div>
            <div className="relative h-2 overflow-hidden rounded-full bg-slate-100">
              {/* Нулевая точка вклада — ориентир для «толкает к отказу / от отказа» */}
              <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" />
              <div
                className="absolute inset-y-0 rounded-full"
                style={
                  positive
                    ? { left: "50%", width: `${halfWidth}%`, backgroundColor: color }
                    : { right: "50%", width: `${halfWidth}%`, backgroundColor: color }
                }
              />
            </div>
          </div>
        );
      })}
      {/* Направление уже видно по цвету каждой полосы выше — эта ось просто напоминает,
          в какую сторону читать «влево/вправо» единообразно для всех строк. */}
      <div className="pt-1">
        <div className="relative h-2">
          <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-slate-200" />
          <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" />
          <span className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-300">&lt;</span>
          <span className="absolute right-0 top-1/2 -translate-y-1/2 text-slate-300">&gt;</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-sm text-slate-400">
          <span>понижает риск отказа</span>
          <span>повышает риск отказа</span>
        </div>
      </div>
    </div>
  );
}
