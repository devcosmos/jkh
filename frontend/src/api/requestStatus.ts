import type { BadgeTone } from "../components/Badge";
import type { MaintenanceRequestStatus } from "./types";

export const REQUEST_STATUS_LABELS: Record<MaintenanceRequestStatus, string> = {
  draft: "Ожидает подтверждения",
  approved: "Утверждена",
  in_progress: "В работе",
  completed: "Выполнена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

export const REQUEST_STATUS_TONE: Record<MaintenanceRequestStatus, BadgeTone> = {
  draft: "warning",
  approved: "neutral",
  in_progress: "neutral",
  completed: "good",
  rejected: "neutral",
  cancelled: "neutral",
};
