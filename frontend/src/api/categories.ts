import type { BadgeTone } from "../components/Badge";

// Категория различает независимо оцениваемые треки прогнозирования (тема 18 CSV с
// ответами организаторов: «два независимых результата, оцениваются отдельно»).
export const CATEGORY_LABELS: Record<string, string> = {
  sensor_failure_pump_fan: "Насос/вентилятор",
  sensor_failure_smoke_gas: "Дым/газ",
};

const CATEGORY_TONES: Record<string, BadgeTone> = {
  sensor_failure_pump_fan: "track-a",
  sensor_failure_smoke_gas: "track-b",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function categoryTone(category: string): BadgeTone {
  return CATEGORY_TONES[category] ?? "neutral";
}

// ModelVersion не хранит category напрямую (только sensor_types через запятую) — те же два
// фиксированных набора типов датчиков, что и в backend/app/workers/replay_worker.py:TRACKS.
export function categoryForSensorTypes(sensorTypes: string): string {
  return sensorTypes.includes("Датчик дыма") || sensorTypes.includes("Газовый датчик")
    ? "sensor_failure_smoke_gas"
    : "sensor_failure_pump_fan";
}
