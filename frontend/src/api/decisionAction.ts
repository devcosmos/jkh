import type { DecisionAction } from "./types";

export const DECISION_ACTION_LABELS: Record<DecisionAction, string> = {
  dispatch: "Направить на проверку",
  observe: "Наблюдать",
  clarify: "Уточнить данные",
  reject: "Отклонить предупреждение",
};
