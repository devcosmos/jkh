interface BarItem {
  key: string;
  label: string;
  value: number;
  colorClass?: string; // полная строка класса, не собирается на лету — см. StatTile.tsx
}

/** Горизонтальный список магнитуд — единая форма для «топ-N» и категориальных разбивок:
 * тонкий трек, скруглённые концы, значение подписано напрямую (не только цветом). */
export function BarList({
  items,
  formatValue = (v: number) => String(v),
  emptyText = "Нет данных",
}: {
  items: BarItem[];
  formatValue?: (v: number) => string;
  emptyText?: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">{emptyText}</p>;
  }
  const max = Math.max(...items.map((i) => i.value), 1);

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
