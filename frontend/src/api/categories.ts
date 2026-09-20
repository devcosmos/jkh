// Категория различает независимо оцениваемые треки прогнозирования (тема 18 CSV с
// ответами организаторов: «два независимых результата, оцениваются отдельно»).
export const CATEGORY_LABELS: Record<string, string> = {
  sensor_failure_pump_fan: "Отказ датчика: насос/вентилятор",
  sensor_failure_smoke_gas: "Отказ датчика: дым/газ",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}
