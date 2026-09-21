import type { DegradationTrendOut } from "../api/types";
import { Badge, type BadgeTone } from "./Badge";

// Обязательная оговорка везде, где показан тренд (docs/ТЗ_тренд_деградации_канала.md,
// раздел 7) — без неё функция создаёт ложное впечатление, что система что-то знает про
// физический износ оборудования, чего на самом деле нет.
const DISCLAIMER =
  "Динамика частоты эпизодов неисправности за последние 90 дней против предыдущих 90 — " +
  "не прогноз износа оборудования (данных о возрасте/дате установки нет), а наблюдаемый " +
  "факт по уже собранной истории.";

const CONFIG: Record<
  DegradationTrendOut["status"],
  { tone: BadgeTone; label: string; muted?: boolean }
> = {
  worsening: { tone: "warning", label: "Учащается ↑" },
  improving: { tone: "good", label: "Реже ↓" },
  stable: { tone: "neutral", label: "Стабильно" },
  insufficient_data: { tone: "neutral", label: "Недостаточно данных", muted: true },
};

export function DegradationTrendBadge({ trend }: { trend: DegradationTrendOut }) {
  const cfg = CONFIG[trend.status];
  const title =
    `${DISCLAIMER}\n\n${trend.recent_count} за последние ${trend.recent_window_days} дней ` +
    `(было ${trend.baseline_count})`;
  return (
    <span title={title} className={cfg.muted ? "opacity-70" : undefined}>
      <Badge tone={cfg.tone}>{cfg.label}</Badge>
    </span>
  );
}
