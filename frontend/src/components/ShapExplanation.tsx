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

// Ширина полосы уже показывает относительный вклад признака среди топ-5, но не то,
// насколько ЭТОТ вклад силён сам по себе — берём цвет по абсолютной величине вклада
// (не по ширине, которая всегда нормирована на максимум среди пяти) и растягиваем на
// фиксированную шкалу, чтобы слабые признаки оставались бледными, а сильные — тёмными,
// даже если все пять в конкретном прогнозе слабые или все сильные.
const CONTRIBUTION_SCALE_MAX = 0.5; // эмпирический потолок «сильного» вклада — выше почти не встречается

function severity(contribution: number): number {
  return Math.min(Math.abs(contribution) / CONTRIBUTION_SCALE_MAX, 1);
}

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
        const t = severity(f.contribution);
        const color = positive ? positiveColor(t) : negativeColor(t);
        return (
          <div key={f.feature}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="text-slate-700">{featureLabel(f)}</span>
              <span className="shrink-0 font-medium text-slate-500">{featureValue(f)}</span>
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
      <p className="flex items-center gap-1 pt-1 text-sm text-slate-400">
        <span className="inline-block h-2 w-2 rounded-full bg-orange-400" />
        повышает риск отказа
        <span className="ml-3 inline-block h-2 w-2 rounded-full bg-sky-400" />
        снижает риск отказа
        <span className="ml-3">— чем темнее, тем сильнее отклонение от нормы</span>
      </p>
    </div>
  );
}
