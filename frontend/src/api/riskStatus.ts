import type { BadgeTone } from "../components/Badge";

export const RISK_STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  observing: "Наблюдение",
  dispatched: "Направлено",
  rejected: "Отклонён",
  resolved: "Решён",
};

export const RISK_STATUS_TONE: Record<string, BadgeTone> = {
  new: "warning",
  observing: "neutral",
  dispatched: "neutral",
  rejected: "neutral",
  resolved: "good",
};
