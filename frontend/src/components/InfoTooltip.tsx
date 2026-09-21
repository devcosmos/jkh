/** Значок «i» рядом с лейблом — поясняет, что вообще означает эта строка, по ховеру.
 * Отдельно от тултипов на самих значениях (например, AnomalyBadge) — те объясняют
 * конкретное текущее значение, этот — сам термин/метрику. */
export function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex shrink-0 cursor-help items-center">
      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-slate-300 text-[9px] leading-none font-semibold text-slate-400">
        i
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 w-64 max-w-[70vw] -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-slate-100 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {text}
      </span>
    </span>
  );
}
