import type { ReactNode } from "react";

// Статусные цвета риска (good/warning/serious/critical) — фиксированный набор, никогда не
// переиспользуется для рабочего статуса или категории/трека (см. dataviz skill: "status
// colors are reserved"). Рабочий статус риск-кейса/заявки — нейтральные оттенки; трек
// (насос/вентилятор vs дым/газ) — фирменный sky против отдельного категориального фиолетового.
export type BadgeTone =
  | "neutral"
  | "good"
  | "warning"
  | "serious"
  | "critical"
  | "track-a"
  | "track-b";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  good: "bg-emerald-50 text-[#0ca30c]",
  warning: "bg-amber-50 text-[#b8790f]",
  serious: "bg-orange-50 text-[#c85f39]",
  critical: "bg-red-50 text-[#d03b3b]",
  "track-a": "bg-sky-50 text-sky-700",
  "track-b": "bg-violet-50 text-violet-700",
};

// Экспортируется отдельно — те же токены используются как заливка баров в BarList
// (frontend/src/components/BarList.tsx), чтобы цвет метки и цвет бара всегда совпадали.
export const TONE_DOT_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-slate-400",
  good: "bg-[#0ca30c]",
  warning: "bg-[#fab219]",
  serious: "bg-[#ec835a]",
  critical: "bg-[#d03b3b]",
  "track-a": "bg-sky-500",
  "track-b": "bg-violet-500",
};
const DOT_CLASSES = TONE_DOT_CLASSES;

export function Badge({
  tone = "neutral",
  dot = false,
  icon,
  children,
}: {
  tone?: BadgeTone;
  /** Статус (рабочее состояние) — круглая точка. */
  dot?: boolean;
  /** Приоритет/серьёзность — треугольник, чтобы не путать с точкой статуса, даже когда
   * тона совпадают. */
  icon?: "priority";
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-sm font-medium ${TONE_CLASSES[tone]}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASSES[tone]}`} />}
      {icon === "priority" && (
        <svg viewBox="0 0 24 24" className="h-2.5 w-2.5 shrink-0" fill="currentColor">
          <path d="M12 3 2 20h20L12 3Z" />
        </svg>
      )}
      {children}
    </span>
  );
}

export function riskPriorityTone(priority: string | null): BadgeTone {
  if (priority === "high") return "critical";
  if (priority === "medium") return "warning";
  return "neutral";
}
