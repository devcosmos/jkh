interface BarItem {
  key: string;
  label: string;
  value: number;
  colorClass?: string; // полная строка класса, не собирается на лету — см. StatTile.tsx
}

/** Горизонтальный список магнитуд — единая форма для «топ-N» и категориальных разбивок.
 * `variant="solid"` (по умолчанию) — тонкий цветной трек рядом с лейблом, цвет несёт
 * категориальный смысл (см. DashboardPage.tsx, colorClass = TONE_DOT_CLASSES). `variant="fill"`
 * — заливка-подложка прямо под текстом от края до края (ModelsPage.tsx), без categorical
 * colorClass: значения тут — просто ранжирование по величине, не категории. */
export function BarList({
  items,
  formatValue = (v: number) => String(v),
  emptyText = "Нет данных",
  variant = "solid",
}: {
  items: BarItem[];
  formatValue?: (v: number) => string;
  emptyText?: string;
  variant?: "solid" | "fill";
}) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">{emptyText}</p>;
  }
  const max = Math.max(...items.map((i) => i.value), 1);

  if (variant === "fill") {
    return (
      <ul className="flex flex-col gap-y-1.5">
        {items.map((item) => {
          const widthPct = Math.max((item.value / max) * 100, item.value > 0 ? 10 : 0);
          return (
            <li key={item.key} className="relative w-full overflow-hidden rounded-lg">
              <span className="relative z-1 flex w-full items-center justify-between gap-x-2 px-2.5 py-1.5 text-sm">
                <span className="truncate text-slate-700">{item.label}</span>
                <span className="shrink-0 font-medium text-slate-500">{formatValue(item.value)}</span>
              </span>
              <div className="absolute inset-y-0 left-0 h-full bg-sky-100" style={{ width: `${widthPct}%` }} />
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="space-y-2.5">
      {items.map((item) => (
        <div key={item.key} className="flex items-center gap-3 text-sm">
          <div className="w-36 shrink-0 truncate text-slate-600" title={item.label}>
            {item.label}
          </div>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-2.5 rounded-full ${item.colorClass ?? "bg-sky-500"}`}
              style={{ width: `${Math.max((item.value / max) * 100, item.value > 0 ? 3 : 0)}%` }}
            />
          </div>
          <div className="w-12 shrink-0 text-right font-semibold text-slate-900">{formatValue(item.value)}</div>
        </div>
      ))}
    </div>
  );
}
