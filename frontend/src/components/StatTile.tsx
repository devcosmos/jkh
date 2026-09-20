import type { ReactNode } from "react";

// Полные строки классов (не собираются на лету из частей) — иначе сканер Tailwind не найдёт
// их в исходниках и не сгенерирует CSS (JIT работает по статическому анализу текста файлов).
const DOT_CLASSES: Record<string, string> = {
  neutral: "bg-slate-400",
  good: "bg-[#0ca30c]",
  warning: "bg-[#fab219]",
  serious: "bg-[#ec835a]",
  critical: "bg-[#d03b3b]",
  "track-a": "bg-sky-500",
  "track-b": "bg-violet-500",
};

const TINT_CLASSES: Record<string, string> = {
  neutral: "bg-slate-100",
  good: "bg-emerald-50",
  warning: "bg-amber-50",
  serious: "bg-orange-50",
  critical: "bg-red-50",
  "track-a": "bg-sky-50",
  "track-b": "bg-violet-50",
};

export function StatTile({
  label,
  value,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: ReactNode;
  tone?: keyof typeof DOT_CLASSES;
  icon?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${TINT_CLASSES[tone]}`}>
        {icon ?? <span className={`h-2.5 w-2.5 rounded-full ${DOT_CLASSES[tone]}`} />}
      </div>
      <div>
        <div className="font-display text-2xl font-semibold leading-none text-slate-900">{value}</div>
        <div className="mt-1 text-xs font-medium text-slate-500">{label}</div>
      </div>
    </div>
  );
}
